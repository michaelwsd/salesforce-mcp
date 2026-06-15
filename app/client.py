import os
import requests
from simple_salesforce import Salesforce


def get_sf_client() -> Salesforce:
    """Create an authenticated Salesforce client.

    Uses OAuth2 client credentials flow if CONSUMER_KEY and CONSUMER_SECRET
    are set. Falls back to username/password/security_token otherwise.
    """
    domain = os.environ["SALESFORCE_DOMAIN"]
    consumer_key = os.getenv("CONSUMER_KEY")
    consumer_secret = os.getenv("CONSUMER_SECRET")

    if consumer_key and consumer_secret:
        token_response = requests.post(
            f"{domain}/services/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": consumer_key,
                "client_secret": consumer_secret,
            },
        )
        token_response.raise_for_status()
        access_token = token_response.json()["access_token"]
        return Salesforce(instance_url=domain, session_id=access_token)

    return Salesforce(
        username=os.environ["SALESFORCE_USERNAME"],
        password=os.environ["SALESFORCE_PASSWORD"],
        security_token=os.environ["SALESFORCE_SECURITY_TOKEN"],
        consumer_key=consumer_key or "",
        consumer_secret=consumer_secret or "",
    )
