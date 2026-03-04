import boto3
import json
import os

def load_secret(event, context):
    secret_name = os.environ["SECRET_NAME"]

    # Create a Secrets Manager client
    client = boto3.client('secretsmanager')

    # We take in a DB secret, get the password, and then reupload the secret
    # with a new entry: "DB_CONNECTION_STRING". This is what our app will use to connect to the database.
    try:
        # Retrieve the secret value
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        secret_string = get_secret_value_response['SecretString']
        secret_dict = json.loads(secret_string)

        # Construct the DB connection string
        db_connection_string = f"postgresql://{secret_dict['username']}:{secret_dict['password']}@{secret_dict['host']}:{secret_dict['port']}/{secret_dict['dbname']}"

        # Update the secret with the new connection string
        secret_dict['db_connection_string'] = db_connection_string
        updated_secret_string = json.dumps(secret_dict)

        client.update_secret(SecretId=secret_name, SecretString=updated_secret_string)
        print(f"Secret '{secret_name}' updated successfully with new value (db_connection_string).")
    except Exception as e:
        print(f"Error loading secret '{secret_name}': {str(e)}")
