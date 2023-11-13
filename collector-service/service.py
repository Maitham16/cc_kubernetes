# Collector service receives frames from the camera and sends them to the other services
# By Maitham Al-rubaye - cloud computing course/ university of Vienna - assignment 1 - WS2023

# Import the required libraries
import logging as logger
from flask import Flask, request, jsonify
from pydantic import BaseModel, ValidationError, Field
import httpx

# Initialize the logger
logger.basicConfig(filename='collector.log', level=logger.INFO)
logger.info('Starting collector service...')

# Initialize camera logger
camera_logger = logger.getLogger('camera_logger')
camera_logger.setLevel(logger.INFO)
file_handler = logger.FileHandler('camera_data.log')
camera_logger.addHandler(file_handler)
camera_logger.propagate = False

# Initialize the Flask app
app = Flask(__name__)

# Define sector service endpoints
sector_service_endpoints = {
    1: "http://sector-service-1:8080/persons",
    2: "http://sector-service-2:8080/persons",
}

# Custom configuration for Pydantic model (To allow the use of '-' in the field names)
class Config:
    alias_generator = lambda field: field.replace('_', '-')
    allow_population_by_field_name = True

# Define Pydantic models
# Frame model
class Frame(BaseModel):
    timestamp: str
    image: str
    section: int
    event: str
    destination: str = None
    extra_info: str = None

# Person model
class Person(BaseModel):
    timestamp: str
    section: int
    event: str
    persons: list
    destination: str = None
    image: str = None
    extra_info: str = None

# KnownPerson model
class KnownPerson(BaseModel):
    timestamp: str
    section: int
    event: str
    known_persons: list
    destination: str = None
    image: str = None
    extra_info: str = None

    class Config(Config):
        pass

# Add a route to the Flask app (function to handle POST requests to /frame)
@app.route('/frame', methods=['POST'])
def add_frame():
    # Initialize the responses dictionary
    responses = {}
    section_responses = {}

    # Get the JSON payload from the request
    try:
        payload = request.json
        frame = Frame(**payload)

         # Prepare a subset of the frame data to send to ImageAnalysis
        frame_subset = {
            "timestamp": frame.timestamp,
            "image": frame.image,
            "section": frame.section,
            "event": frame.event
        }

        # Send frame to ImageAnalysis
        try:
            # logging the start of sending frame to ImageAnalysis
            logger.info("Sending frame to ImageAnalysis")

            # Send data to ImageAnalysis service for analysis
            r1 = httpx.post("http://image-analysis-service:8080/frame", json=frame_subset)

            # Check the response status code
            if r1.status_code == 200:
                # Add the response to the responses dictionary
                responses['ImageAnalysis'] = r1.json()
                # logging the success of sending frame to ImageAnalysis
                logger.info("Frame sent to ImageAnalysis successfully")
                
                # Send data to Section service for statistics
                person = Person(
                    timestamp=frame.timestamp,
                    section=frame.section,
                    event=frame.event,
                    persons=r1.json().get('persons', []),
                    image=frame.image
                )

                # Send data to Section service
                # logging the start of sending data to Section service
                logger.info("Sending data to Section service")

                # Determine the endpoint for the section service
                section_endpoint = sector_service_endpoints.get(frame.section)
                if section_endpoint:
                    try:
                        logger.info(f"Sending data to Section service for section {frame.section}")

                        r_section = httpx.post(section_endpoint, json=person.dict())

                        if r_section.status_code == 200:
                            section_responses[f'Section {frame.section}'] = "Data sent successfully"
                            logger.info(f"Data sent to Section {frame.section} service successfully")
                        else:
                            section_responses[f'Section {frame.section}'] = f"Error: {r_section.status_code}"
                            logger.info(f"Failed to send data to Section {frame.section} service: {r_section.status_code}")

                    except Exception as e:
                        section_responses[f'Section {frame.section}'] = f"Failed to process frame on section service: {str(e)}"
                        logger.info(f"Failed to send frame to Section {frame.section} service: {str(e)}")
                else:
                    logger.info(f"No endpoint defined for Section {frame.section}")

            else:
                # Add the response to the responses dictionary
                responses['ImageAnalysis'] = f"Error: {r1.status_code}"
                # logging the failure of sending frame to ImageAnalysis service 
                logger.info(f"Failed to send frame to ImageAnalysis: {r1.status_code}")

        except Exception as e:
            # Add the response to the responses dictionary
            responses['ImageAnalysis'] = f"Failed to process frame on r1: {str(e)}"
            # logging the failure of sending frame to ImageAnalysis service
            logger.info(f"Failed to send frame to ImageAnalysis: {str(e)}")

       # Send frame to FaceRecognition
        try:
            # logging the start of sending frame to FaceRecognition
            logger.info("Sending frame to FaceRecognition")

            # Send data to FaceRecognition service for analysis
            r2 = httpx.post("http://face-recognition-service:8080/frame", json=frame_subset)

            # Check the response status code
            if r2.status_code == 200:
                # Add the response to the responses dictionary
                responses['FaceRecognition'] = r2.json()
                # logging the success of sending frame to FaceRecognition
                logger.info("Frame sent to FaceRecognition successfully")

                # Prepare the known_person payload for the alerts
                known_person_data = {
                    "timestamp": frame.timestamp,
                    "section": frame.section,
                    "event": frame.event,
                    "known_persons": r2.json().get('known-persons', []),
                    "image": frame.image,
                    "extra_info": frame.extra_info
                }

                # Send data to alerts
                r_alert = httpx.post("http://alert-service:8080/alerts", json=known_person_data)

                # Check the response status code
                if r_alert.status_code == 200:
                    # logging the success of adding known person to alerts
                    logger.info("Successfully added known person to alerts.")
                else:
                    # logging the failure of adding known person to alerts
                    logger.info(f"Failed to add known person to alerts: {r_alert.status_code}")

            else:
                # Add the response to the responses dictionary 
                responses['FaceRecognition'] = f"Error: {r2.status_code}"
                # logging the failure of sending frame to FaceRecognition
                logger.info(f"Failed to send frame to FaceRecognition: {r2.status_code}")

        except Exception as e:
            # Add the response to the responses dictionary
            responses['FaceRecognition'] = f"Failed to process frame on r2: {str(e)}"
            # logging the failure of sending frame to FaceRecognition service 
            logger.info(f"Failed to send frame to FaceRecognition: {str(e)}")

        # Prepare the responses dictionary
        all_responses = {
            "responses": responses,
            "section_responses": section_responses
        }

        # Log the received frame data to camera_data.log
        camera_logger.info(f"Received Frame: {frame.dict()}")
        # Return the responses dictionary as JSON
        return jsonify(all_responses), 200 if all_responses else 400

    except ValidationError as e:
        # return the validation error messages as JSON if the JSON payload is not valid (does not match the model)
        return jsonify({"detail": "Validation Error", "errors": e.errors()}), 400
    except Exception as e:
        # return the error message if any other error occurs
        return jsonify({"detail": "Failed to process frame", "error": str(e)}), 400

# Run the Flask app
if __name__ == '__main__':
    # Run the Flask app on port 8080
    app.run(host='0.0.0.0', port=8080)