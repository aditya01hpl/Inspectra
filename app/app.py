from chatbot import VehicleChatbot
import json
DB_CONFIG = {
    "dbname": "vehicle_inspection_db",
    "user": "postgres",
    "password": "1234",
    "host": "localhost",
    "port": "5432"
}

def main():
    chatbot = VehicleChatbot(DB_CONFIG)
    
    print("Vehicle Inspection Chatbot (type 'exit' to quit)")
    while True:
        try:
            query = input("\nYour query: ")
            if query.lower() in ['exit', 'quit']:
                break
                
            response = chatbot.process_query(query)
            print("\n" + "="*50)
            print(response)
            print("="*50)
        except KeyboardInterrupt:
            break
    
    chatbot.close()
    print("Session ended")

if __name__ == "__main__":
    main()