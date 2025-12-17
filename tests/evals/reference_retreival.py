import requests
import json
import os

# Define the base URL of your Policy Atlas instance
BASE_URL = "http://localhost:8000"

# Get the authentication token from an environment variable
# Replace this with your actual token for testing
AUTH_TOKEN = os.getenv("POLICY_ATLAS_TOKEN",
"eyJhbGciOiJSUzI1NiIsImNhdCI6ImNsX0I3ZDRQRDExMUFBQSIsImtpZCI6Imluc18yeTBXWmdWMzAzamRhWlBabVNjWFVxdmhrdHUiLCJ0eXAiOiJKV1QifQ.eyJhenAiOiJodHRwOi8vbG9jYWxob3N0OjMwMDAiLCJleHAiOjE3NjAwOTQxNTQsImZ2YSI6WzQ0NDMsLTFdLCJpYXQiOjE3NjAwOTQwOTQsImlzcyI6Imh0dHBzOi8vYnVzeS1zaWxrd29ybS02LmNsZXJrLmFjY291bnRzLmRldiIsIm5iZiI6MTc2MDA5NDA4NCwic2lkIjoic2Vzc18zM2pQVDlhbGFaQ09KOHo5YjFzdkN1ampEWGUiLCJzdHMiOiJhY3RpdmUiLCJzdWIiOiJ1c2VyXzJ6MDVlTUd6SW1yOG02VFFGbmJiMmphTHdWayIsInYiOjJ9.Q7VbB-tm07oIuETYe1fmlI4xGgKpwvOdyLddWRrJ5THSqdUCi3VzfiBBtAzwjzx7vCDF5bplH0_wMe33Wac73XZqG5pF67ESmYlas2cZHkgLOA9mzZRLGTSJERTRQpAQ42sLAJlKSa0Ub1eVt2nrkhyHSXa-Ksuk62NLUbpDBxxtsPj_a7pWf8mHSheDWHpJnW_JbYD_TAjxiw2V-NBwoI92DTOWD9aGC-rSbkd9y-MdJyaTO5ehTCZMU1N2EuiU5eTpLfp_9vIBuO8cygZWdGeN3WriyTbFMeHE7cqwdswZa2_ebNEVFbthR9Ql5RbbjSGU6Vwj6VRLs0e5Gu2K5g"
)

def create_project(title, description):
    """
    Creates a new project in Policy Atlas.
    """
    url = f"{BASE_URL}/api/analysis-projects/"
    payload = {
        "title": title,
        "description": description
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AUTH_TOKEN}"
    }
    response = requests.post(url, data=json.dumps(payload), headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error creating project: {response.status_code} - {response.text}")
        return None

def run_analysis(project_id, boolean_query):
    """
    Runs an analysis on a project with a custom boolean query.
    """
    url = f"{BASE_URL}/api/analysis-projects/{project_id}/run-analysis"
    payload = {
        "query": "What is the effect of free school meals on obesity and calorie consumption in children?",
        "mode": "boolean",
        "boolean_query": boolean_query,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AUTH_TOKEN}"
    }
    response = requests.post(url, data=json.dumps(payload), headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error running analysis: {response.status_code} - {response.text}")
        return None

if __name__ == "__main__":
    if AUTH_TOKEN == "YOUR_AUTH_TOKEN_HERE":
        print("Please set your authentication token in the script or as an environment variable.")
    else:
        # 1. Create a new project
        project_title = "Relevance Check Evaluation"
        project_description = "Supermarket access custom boolean 200."
        project = create_project(project_title, project_description)

        if project:
            project_id = project.get("id")
            print(f"Successfully created project with ID: {project_id}")

            # 2. Run the analysis with a custom boolean query
            custom_query = '\
            (supermarket OR "food environment" OR "grocery store" OR "retail food environment") AND (access* OR zoning* OR "Access to Healthy Foods") AND (obesity OR overweight OR "over-weight" OR BMI OR "body weight" OR bodyweight OR "Body mass index") AND ("systematic review" OR systematic* OR "meta-analys*" OR "narrative synthes*")'
            analysis_results = run_analysis(project_id, custom_query)

            if analysis_results:
                print("\nAnalysis Results:")
                print(json.dumps(analysis_results, indent=2))