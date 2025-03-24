from airflow import DAG
from airflow.providers.http.hooks.http import HttpHook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.decorators import task
from airflow.utils.dates import days_ago
import logging

# Constants
LATITUDE = '51.5074'
LONGITUDE = '-0.1278'
POSTGRES_CONN_ID = 'postgres_default'
API_CONN_ID = 'open_meteo_api'

default_args = {
    'owner': 'airflow',
    'start_date': days_ago(1),
}

# Define the DAG
with DAG(
    dag_id='weather_etl_pipeline',
    default_args=default_args,
    schedule_interval='@daily',
    catchup=False,
    description='ETL pipeline to fetch weather data and store in Postgres'
) as dag:

    @task()
    def extract_weather_data():
        """Extract weather data from Open-Meteo API using Airflow HTTP connection"""
        http_hook = HttpHook(http_conn_id=API_CONN_ID, method='GET')
        endpoint = f'/v1/forecast?latitude={LATITUDE}&longitude={LONGITUDE}&current_weather=true'
        ## https://api.open-meteo.com/v1/forecast?latitude=51.5074&longitude=-0.1278&current_weather=true

        try:
            response = http_hook.run(endpoint)
            if response.status_code == 200:
                logging.info("Weather data fetched successfully.")
                return response.json()
            else:
                raise Exception(f"Failed to fetch data: {response.status_code} - {response.text}")
        except Exception as e:
            logging.error(f"API request failed: {e}")
            raise

    @task()
    def transform_weather_data(weather_data):
        """Transform the extracted weather data"""
        current_weather = weather_data.get('current_weather', {})
        if not current_weather:
            raise ValueError("Missing 'current_weather' data in the API response.")
        
        transformed_data = {
            'latitude': LATITUDE,
            'longitude': LONGITUDE,
            'temperature': current_weather.get('temperature'),
            'windspeed': current_weather.get('windspeed'),
            'winddirection': current_weather.get('winddirection'),
            'weathercode': current_weather.get('weathercode')
        }

        logging.info(f"Transformed weather data: {transformed_data}")
        return transformed_data

    @task()
    def load_weather_data(transformed_data):
        """Load transform data into PostgreSQL."""
        pg_hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        conn = pg_hook.get_conn()
        cursor = conn.cursor()

        # Create a table if it does not exist
        cursor.execute("""
    CREATE TABLE IF NOT EXISTS weather (
        latitude VARCHAR,
        longitude VARCHAR,
        temperature FLOAT,
        windspeed FLOAT,
        winddirection FLOAT,
        weathercode INTEGER,
        "timestamp" TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

        # Insert transformed data into the table
        cursor.execute("""
        INSERT INTO weather (latitude, longitude, temperature, windspeed, winddirection, weathercode)
        VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            transformed_data['latitude'],
            transformed_data['longitude'],
            transformed_data['temperature'],
            transformed_data['windspeed'],
            transformed_data['winddirection'],
            transformed_data['weathercode']
        ))

        conn.commit()
        cursor.close()

        ## DAG Worflow- ETL Pipeline
    weather_data= extract_weather_data()
    transformed_data=transform_weather_data(weather_data)
    load_weather_data(transformed_data)



