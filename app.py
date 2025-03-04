from flask import Flask, request, jsonify, render_template
import requests
from zeep import Client
from zeep.transports import Transport
from requests.auth import HTTPBasicAuth
from requests.exceptions import ConnectionError, Timeout, RequestException

app = Flask(__name__)

# Constants for SAP Service
SAP_WSDL_URL = "http://SAP-APPS.ceb.local:8000/sap/bc/srt/wsdl/flv_10002A111AD1/bndg_url/sap/bc/srt/rfc/sap/zchangesappassword/100/zchangesappassword_serv/zchangesappassword_bind?sap-client=100"
SAP_USERNAME = "Ztest1"
SAP_PASSWORD = "Ceb$1234"

# Chatbot state
chat_context = None
verification_stage = 0
user_details = {}
previous_state = None
state_history = []

def chatbot_response(user_input):
    """Handle chatbot logic based on user input."""
    global chat_context, verification_stage, user_details, previous_state, state_history

    # Handle "Home" button
    if user_input.lower() == "home":
        # Reset all chatbot state variables
        chat_context = None
        verification_stage = 0
        user_details = {}
        previous_state = None
        state_history = []
        # Return the main menu with the 4 clickable buttons
        return "Main menu. Select an option.", ["Reset an application password", "Hardware help", "Need more assistance", "Ask for a resource"]

    # Handle "Back" button
    if user_input.lower() == "back":
        if state_history:
            previous_state = state_history.pop()
            if previous_state == "main_menu":
                verification_stage = 0
                chat_context = None
                return "Main menu. Select an option.", ["Reset an application password", "Hardware help", "Need more assistance", "Ask for a resource"]
            elif previous_state == "password_reset":
                verification_stage = 1
                chat_context = "password_reset"
                return "Select an application for password reset.", ["SAP", "FET", "MR App", "Naveo", "Back"]
            elif previous_state == "SAP_locked":
                verification_stage = 2
                chat_context = "SAP"
                return "Is your SAP account locked? (yes/no)", ["yes", "no", "Back"]
            elif previous_state == "SAP_reset":
                verification_stage = 3
                chat_context = "SAP"
                return "Do you need to reset your password? (yes/no)", ["yes", "no", "Back"]
            elif previous_state == "SAP_email":
                verification_stage = 4
                chat_context = "SAP"
                return "What is your email address?", ["Back"]
            elif previous_state == "hardware_options":
                return "Select a type of hardware for assistance.", ["Mouse", "CPU", "Keyboard", "Desktop PC", "Laptop", "Back"]
            elif previous_state == "assistance_categories":
                return "Please categorize your issue.", ["Application", "Hardware", "Administrative", "Other", "Back"]
            elif previous_state == "resource_topics":
                return "Select a topic for resource assistance.", ["Application", "Mail", "Active Directory", "Back"]
        else:
            return "No previous state to return to.", []

    # Main chatbot logic
    if verification_stage == 0:
        if user_input == "Reset an application password":
            chat_context = "password_reset"
            verification_stage = 1
            previous_state = "main_menu"
            state_history.append(previous_state)
            return "Select an application for password reset.", ["SAP", "FET", "MR App", "Naveo", "Back"]
        elif user_input == "Hardware help":
            previous_state = "main_menu"
            state_history.append(previous_state)
            return "Select a type of hardware for assistance.", ["Mouse", "CPU", "Keyboard", "Desktop PC", "Laptop", "Back"]
        elif user_input == "Need more assistance":
            previous_state = "main_menu"
            state_history.append(previous_state)
            return "Please categorize your issue.", ["Application", "Hardware", "Administrative", "Other", "Back"]
        elif user_input == "Ask for a resource":
            previous_state = "main_menu"
            state_history.append(previous_state)
            return "Select a topic for resource assistance.", ["Application", "Mail", "Active Directory", "Back"]
        else:
            return "I didn't understand that. Please select an option.", ["Reset an application password", "Hardware help", "Need more assistance", "Ask for a resource"]

    elif verification_stage == 1 and chat_context == "password_reset":
        if user_input in ["SAP", "FET", "MR App", "Naveo"]:
            if user_input == "SAP":
                chat_context = "SAP"
                verification_stage = 2
                state_history.append("password_reset")
                return "Is your SAP account locked? (yes/no)", ["yes", "no", "Back"]
            else:
                verification_stage = 0
                return f"You selected {user_input}. Please provide your registered email address.", ["Back"]
        else:
            return "Please select a valid application.", ["SAP", "FET", "MR App", "Naveo", "Back"]

    elif verification_stage == 2 and chat_context == "SAP":
        if user_input in ["yes", "no"]:
            if user_input == "yes":
                verification_stage = 3
                state_history.append("SAP_locked")
                return "Do you need to reset your password? (yes/no)", ["yes", "no", "Back"]
            else:
                verification_stage = 7
                state_history.append("SAP_issue")
                return "What type of issue are you encountering on SAP?", ["Back"]
        else:
            return "Please answer with 'yes' or 'no'.", ["yes", "no", "Back"]

    elif verification_stage == 3 and chat_context == "SAP":
        if user_input in ["yes", "no"]:
            if user_input == "yes":
                verification_stage = 4
                state_history.append("SAP_reset")
                return "What is your email address?", ["Back"]
            else:
                verification_stage = 0
                return "Alright, let me know if you need help with anything else.", []
        else:
            return "Please answer with 'yes' or 'no'.", ["yes", "no", "Back"]

    elif verification_stage == 4 and chat_context == "SAP":
        user_details['email'] = user_input
        verification_stage = 5
        state_history.append("SAP_email")
        return "What is your mobile number?", ["Back"]

    elif verification_stage == 5 and chat_context == "SAP":
        user_details['mobile'] = user_input
        verification_stage = 0
        response_message = send_to_sap_service(user_details['email'], user_details['mobile'])
        return response_message, []

    elif verification_stage == 7 and chat_context == "SAP":
        return "Please contact the IT support team for further assistance.", []

    elif previous_state == "hardware_options":
        return f"You selected {user_input}. Please describe the issue you're facing.", ["Back"]

    elif previous_state == "assistance_categories":
        return f"You selected {user_input}. Please provide further details about the issue.", ["Back"]

    elif previous_state == "resource_topics":
        return f"You selected {user_input}. Please provide details about the resource you need.", ["Back"]

    else:
        return "I didn't understand that. Please try again.", []

def send_to_sap_service(email, mobile):
    """Send user details to the SAP service and handle exceptions."""
    try:
        session = requests.Session()
        session.auth = HTTPBasicAuth(SAP_USERNAME, SAP_PASSWORD)
        transport = Transport(session=session)
        client = Client(SAP_WSDL_URL, transport=transport)
        service = client.bind('zchangesappassword_serv', 'zchangesappassword_bind')
        response = service.ZFM_CHANGE_SAP_PASSWORD(EMAIL=email, MOBNUMBER=mobile)
        print("SAP Service Response:", response)
        return "Details have been sent to the SAP service successfully."
    except ConnectionError:
        return "Unable to reach SAP service. Please check your connection or try again later."
    except Timeout:
        return "The request to SAP service timed out. Please try again later."
    except RequestException as e:
        return f"An error occurred while trying to contact SAP service: {str(e)}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@app.route('/')
def home():
    """Serve the chatbot webpage."""
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    """Handle chatbot requests."""
    user_input = request.json.get('message')
    if not user_input:
        return jsonify({'response': "Please provide a valid input.", 'options': []})

    response, options = chatbot_response(user_input)
    return jsonify({'response': response, 'options': options})

if __name__ == '__main__':
    app.run(debug=True)