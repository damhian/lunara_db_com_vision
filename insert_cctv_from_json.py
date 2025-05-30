import json
import uuid
from sqlalchemy.orm import sessionmaker
from app.db import engine
from app.models import MsCCTV
from tkinter import filedialog

def clean_coordinate(coord):
    if not coord: 
        return None
    try:
        coord = coord.replace(".", "")
        return float(coord) / 1e6
    except:
        print(f"Invalid coordinate value: {coord}")
        return None

# Function to insert data from a JSON file into the Ms_CCTV table
def insert_data_from_json(file_path):
    # Open and parse the JSON file
    
    file_path = filedialog.askopenfilename(
        title="Select JSON File",
        filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
    )
    
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        # Extract the resource list
        # resources = data.get("data", {}).get("resource", [])
        resources = data.get("data", [])

        if not resources:
            print("No resources found in the JSON file.")
            return

        # Create a new SQLAlchemy session
        Session = sessionmaker(bind=engine)
        session = Session()

        try:
            for resource in resources:
                latitude = clean_coordinate(resource.get("lat"))
                longitude = clean_coordinate(resource.get("long"))                
                
                new_cctv = MsCCTV(
                    id=uuid.uuid4(),  # Generate a new UUID
                    nama_lokasi=resource.get("nama_lokasi"),
                    nama_cctv=resource.get("nama_cctv"),
                    stream_url=resource.get("stream_url"),
                    status=resource.get("status"),
                    nama_pengelola=resource.get("nama_pengelola"),
                    protocol=resource.get("protocol"),
                    latitude=resource.get("latitude"),
                    longitude=resource.get("longitude"),
                    source=resource.get("source"),
                    tag_kategori=resource.get("tag_kategori"),
                    matra=resource.get("matra"),
                    nama_kabupaten_kota=resource.get("nama_kabupaten_kota"),
                    nama_provinsi=resource.get("nama_provinsi")
                )

                # Add the object to the session
                session.add(new_cctv)

            # Commit the session to save all changes
            session.commit()
            print("Data inserted successfully!")

        except Exception as e:
            # Rollback the session if there's an error
            session.rollback()
            print(f"An error occurred: {e}")

        finally:
            # Close the session
            session.close()

    except FileNotFoundError:
        print(f"File not found: {file_path}")
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON file: {e}")

# Path to the JSON file
file_path = "path_to_your_file.json"

# Call the function
insert_data_from_json(file_path)
