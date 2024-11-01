import os
import pandas as pd
import time
import random
from openai import OpenAI
from GoogleNews import GoogleNews
from datetime import datetime
import logging
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('survey.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Get API key from environment
api_key = os.getenv('api_key4')
if not api_key:
    raise ValueError("API key not found in environment variables")

# Initialize the OpenAI client with the API key
client = OpenAI(api_key=api_key)

try:
    # Load the Questions data from Excel file
    questions_df = pd.read_excel('Questions_daily.xlsx')
    logging.info("Successfully loaded Questions_daily.xlsx")
except Exception as e:
    logging.error(f"Error loading Questions_daily.xlsx: {str(e)}")
    raise

# Extract the questions into a dictionary
questions = dict(zip(questions_df['Q_id'], questions_df['Question']))

# Define the number of runs for each assistant
num_personas = 3  # Total number of runs
num_per_group = num_personas // 3  # Number of runs per group

# Define the run identifier
Run = 1

# Assistant IDs
assistants = {
    "Assistant_4omini": "asst_mEqNb9vFNvo76T6aid77qD0R",
    "Assistant_4o": "asst_ZOelTI0EortnsJA0z1CIElnM"
}

# Define instructions
general_instructions = "The GPT is designed to answer users' questions about the expectations for future inflation. It responds with numerical percentage estimates, reflecting its opinions and anticipations about inflation while acknowledging the inherent uncertainty in such forecasts. It presents answers in two formats: single percentage points for point prediction and a list of percentages for probability distribution questions. The GPT ensures responses are solely numerical and not any written statements with the alphabets and formatted accordingly: for point prediction, it uses [\_\_\_ \%,] and for probability distribution questions, it uses [\_\_\_ \%,\_\_\_ \%,\_\_\_ \%,\_\_\_ \%,\_\_\_ \%,\_\_\_ \%,\_\_\_ \%,\_\_\_ \%,\_\_\_ \%,\_\_\_ \%,]."

def get_news(topic):
    """Fetch news articles about a specific topic"""
    try:
        googlenews = GoogleNews(lang='en', region='US')
        googlenews.search(topic)
        results = googlenews.results()
        news_text = ""
        for result in results:
            news_text += f"Title: {result['title']}\nDescription: {result['desc']}\n\n"
        logging.info(f"Successfully fetched news for topic: {topic}")
        return news_text
    except Exception as e:
        logging.error(f"Error fetching news for {topic}: {str(e)}")
        return f"Error fetching news: {str(e)}"

def get_response(thread_id, assistant_id, content, instructions):
    """Get response from OpenAI assistant"""
    try:
        my_thread_message = client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=content
        )
        
        my_run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
            instructions=instructions
        )
        
        while True:
            keep_retrieving_run = client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=my_run.id
            )
            if keep_retrieving_run.status == "completed":
                all_messages = client.beta.threads.messages.list(
                    thread_id=thread_id
                )
                return all_messages.data[0].content[0].text.value
            elif keep_retrieving_run.status == "failed":
                raise Exception("Assistant run failed")
            time.sleep(1)
    except Exception as e:
        logging.error(f"Error getting response: {str(e)}")
        raise

def process_batch(assistant_name, assistant_id):
    """Process a batch of surveys for a specific assistant"""
    results = []
    
    try:
        # Get news content once for each type
        logging.info("Fetching news content...")
        inflation_news = get_news('Inflation')
        election_news = get_news('Election')
        
        # Create a list with equal distribution of groups
        groups = [0] * num_per_group + [1] * num_per_group + [2] * num_per_group
        random.shuffle(groups)  # Randomize the order
        
        for i, group in enumerate(groups):
            try:
                # Create a Thread
                my_thread = client.beta.threads.create()
                
                # If not control group, provide news context
                if group == 1:
                    context = inflation_news
                    get_response(my_thread.id, assistant_id, context, "Please read this context before answering the following questions.")
                elif group == 2:
                    context = election_news
                    get_response(my_thread.id, assistant_id, context, "Please read this context before answering the following questions.")
                
                # Initialize the result row
                result_row = [Run, group]
                
                # Initial questions (Q1_I to Q5_I)
                initial_responses = []
                initial_prompts = []
                for q in ['Q1_I', 'Q2_I', 'Q3_I', 'Q4_I', 'Q5_I']:
                    question = questions[q]
                    response = get_response(my_thread.id, assistant_id, question, general_instructions)
                    initial_responses.append(response)
                    initial_prompts.append(question)
                
                # Add responses and prompts to the result row
                result_row.extend(initial_responses)
                result_row.extend(initial_prompts)
                result_row.append(general_instructions)
                
                # Add the context provided (if any)
                context_provided = ""
                if group == 1:
                    context_provided = inflation_news
                elif group == 2:
                    context_provided = election_news
                result_row.append(context_provided)
                
                results.append(result_row)
                
                logging.info(f"Processed: Assistant: {assistant_name}, Run {i+1}/{num_personas}, Group: {group}")
                
            except Exception as e:
                logging.error(f"Error processing run {i+1} for {assistant_name}: {str(e)}")
                continue
                
    except Exception as e:
        logging.error(f"Error in process_batch for {assistant_name}: {str(e)}")
        raise
        
    return results

def main():
    """Main function to run the survey"""
    try:
        for assistant_name, assistant_id in assistants.items():
            logging.info(f"\nStarting processing for {assistant_name}")
            results = process_batch(assistant_name, assistant_id)
                
            # Save results with current date and time
            current_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            columns = ['Run', 'Group'] + \
                     ['Q1_I', 'Q2_I', 'Q3_I', 'Q4_I', 'Q5_I'] + \
                     ['Prompt_Q1_I', 'Prompt_Q2_I', 'Prompt_Q3_I', 'Prompt_Q4_I', 'Prompt_Q5_I'] + \
                     ['Instructions', 'Context']
            
            df_final = pd.DataFrame(results, columns=columns)
            filename = f'results_{assistant_name}_run{Run}_{current_datetime}.xlsx'
            df_final.to_excel(filename, index=False)
            logging.info(f"Results for {assistant_name} saved to {filename}")
            
            if assistant_name != list(assistants.keys())[-1]:  # If not the last assistant
                logging.info("Waiting for 5 seconds before processing next assistant...")
                time.sleep(5)
                
    except Exception as e:
        logging.error(f"Error in main function: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"Script failed: {str(e)}")
        sys.exit(1)
