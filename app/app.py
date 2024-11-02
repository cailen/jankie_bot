import json
import praw
import boto3
from botocore.exceptions import ClientError
import logging
import os

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
logger.info(f"DRY_RUN: {DRY_RUN}")

SUBREDDIT = os.environ.get("SUBREDDIT", "jankie_test")
logger.info(f"Subreddit: {SUBREDDIT}")

# Boto3 session using 1password
session = boto3.session.Session()

# Initialize AWS Parameter Store for storing the last comment ID
ssm_client = session.client(
    service_name="ssm",
    region_name="us-east-1",
)
LAST_COMMENT_ID_SECRET_NAME = "/jankie/reddit/last_comment_id"
CREDS_SECRET_NAME = "/jankie/reddit/creds"

creds = ssm_client.get_parameter(Name=CREDS_SECRET_NAME, WithDecryption=True)["Parameter"]["Value"]
creds = json.loads(creds)

# Initialize PRAW without username/password
reddit = praw.Reddit(
    client_id=creds.get("client_id"),
    client_secret=creds.get("client_secret"),
    user_agent=creds.get("user_agent"),
    username=creds.get("username"),
    password=creds.get("password"),
)

logging.info(reddit.user.me())

# Step 2: Define phrases to look for and responses
response_dict = {
    "jankie": [
        "WE'RE VIBING!",
        "J-A-N! K-I-E! JANKIE! JANKIE! LET'S PARTY!",
        "Ice cream, pizza, so much fun!",
        "I love having fun! Do you like having F-U-N fun?",
        "I am sooooo excited!",
    ],
    "hey everyone!": [
        "Hey, I'm Jankie! Let's have some fun!",
        "It's so fun to have friends!",
        "Hi there! I am sooooooooo excited to meet you!",
    ],
}

# Define the subreddit and keyword to search for
subreddit = reddit.subreddit(SUBREDDIT)


def lambda_handler(event, context):
    logger.info("Lambda function started")

    # Retrieve the last processed comment ID from Parameter Store
    last_comment_id = get_last_comment_id()
    logger.info(f"Retrieved last comment ID: {last_comment_id}")

    # Fetch the latest 100 comments
    comments = list(subreddit.comments(limit=100))
    new_last_comment_id = last_comment_id
    eligible_comments = []

    # Filter comments for the keyword
    for comment in comments:
        # Stop if we reach already processed comments
        if last_comment_id and comment.id <= last_comment_id:
            logger.info("Reached already processed comments. Stopping check.")
            break

        if check_comment_eligibility(comment, response_dict):
            logger.info(f"Phrase found in comment or reply by {comment.author} ({comment.id})")
            eligible_comments.append(comment)

        # Update the latest comment ID to avoid reprocessing
        new_last_comment_id = max(new_last_comment_id, comment.id)

    # Reply to a random eligible comment
    if eligible_comments:
        comment = eligible_comments[hash(new_last_comment_id) % len(eligible_comments)]
        if not DRY_RUN:
            reply_to_comment(comment, response_dict)
        else:
            logger.info(
                f"DRY RUN: Would have replied to comment by {comment.author}: {comment.body} ({comment.id})"
            )

    # Store the latest comment ID for the next invocation
    if new_last_comment_id:
        if not DRY_RUN:
            save_last_comment_id(new_last_comment_id)
            logger.info(f"Updated last comment ID to: {new_last_comment_id}")
        else:
            logger.info(
                f"DRY RUN: Would have saved last comment ID: {new_last_comment_id}"
            )

    logger.info("Lambda function completed")
    return {"statusCode": 200, "body": json.dumps("Completed check for keyword.")}


def check_comment_eligibility(comment, response_dict):
    """
    Checks the comment for phrases.
    Returns True if the keyword is found in the comment.
    """
    for phrase, responses in response_dict.items():
        if phrase.lower() in comment.body.lower():
            logger.info(f"Found comment by {comment.author}: {comment.body} ({comment.id})")
            return True
    return False


def reply_to_comment(comment, response_dict):
    """
    Replies to a comment with a random response from the response_dict.
    Returns True if successfully replied to.
    """
    for phrase, responses in response_dict.items():
        if phrase.lower() in comment.body.lower():
            response_message = responses[hash(comment.id) % len(responses)]
            logger.info(f"Responding with: {response_message} to comment by {comment.author} ({comment.id})")
            comment.reply(response_message)
            return True
    return False


def get_last_comment_id():
    try:
        response = ssm_client.get_parameter(Name=LAST_COMMENT_ID_SECRET_NAME, WithDecryption=True)
        logger.info("Successfully retrieved the last comment ID")
        last_comment_id = response["Parameter"]["Value"]
        logger.info(
            f"Last comment ID retrieved from Parameter Store: {last_comment_id}"
        )
        return last_comment_id
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            logger.warning(
                "No last comment ID found in Parameter Store. Assuming no comments have been processed yet."
            )
            return None
        else:
            logger.error(f"Error retrieving last comment ID from Parameter Store: {e}")
            raise


def save_last_comment_id(comment_id):
    try:
        ssm_client.put_parameter(
            Name=LAST_COMMENT_ID_SECRET_NAME,
            Value=comment_id,
            Type="String",
            Overwrite=True,
        )
        logger.info(f"Last comment ID saved to Parameter Store: {comment_id}")
    except ClientError as e:
        logger.error(f"Failed to save last comment ID to Parameter Store: {e}")
        raise Exception(f"Failed to save last comment ID: {e}")


# Step 5: Run the bot
if __name__ == "__main__":
    try:
        logging.info("Starting the bot...")
        lambda_handler(None, None)
        logging.info("Bot completed successfully.")
    except Exception as e:
        logger.error(f"Encountered an error: {e}")
