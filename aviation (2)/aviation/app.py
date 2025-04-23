from flask import Flask, render_template, request
import requests
from datetime import datetime
import os
from dotenv import load_dotenv
from metar import Metar
from geopy.geocoders import Nominatim

load_dotenv()
app = Flask(__name__)
#API_KEY = os.getenv('AVIATION_WEATHER_API_KEY', '')


def get_airport_coordinates(airport_id):
    """Fetch coordinates for any ICAO code using AviationAPI or Nominatim"""
    # Option 1: Use AviationAPI (requires API key)
    try:
        url = f"https://aviation-api.com/api/v1/airports?icao={airport_id}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data and isinstance(data, list) and data[0].get('lat'):
                return (float(data[0]['lat']), float(data[0]['lon']))
    except:
        pass
    
    # Option 2: Fallback to Nominatim (OpenStreetMap)
    try:
        geolocator = Nominatim(user_agent="flight_weather_app")
        location = geolocator.geocode(f"{airport_id} Airport")
        if location:
            return (location.latitude, location.longitude)
    except:
        pass
    
    # Final fallback: Return (0, 0) if no coordinates found
    return (0, 0)




def fetch_weather_data(station_id, data_type):
    """Fetch METAR or TAF data from Aviation Weather API"""
    base_url = "https://aviationweather.gov/api/data/"
    
    if data_type == 'metar':
        url = f"{base_url}metar?ids={station_id}&format=json"
    elif data_type == 'taf':
        url = f"{base_url}taf?ids={station_id}&format=json"
    else:
        return None
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {data_type.upper()} data: {e}")
        return None

def parse_metar(metar_data):
    """Parse and decode METAR data with sophisticated parsing"""
    if not metar_data or not isinstance(metar_data, list) or len(metar_data) == 0:
        return None
    
    raw_metar = metar_data[0].get('rawOb', '')
    if not raw_metar:
        return None
    
    try:
        metar_obj = Metar.Metar(raw_metar)
        
        # Format clouds information
        clouds = []
        if metar_obj.sky:
            for layer in metar_obj.sky:
                cover = layer[0] if layer[0] else "N/A"
                height = f"{layer[1].value():.0f} ft" if layer[1] else "N/A"
                cloud_type = layer[2] if layer[2] else ""
                clouds.append(f"{cover} at {height} {cloud_type}")
            clouds_str = ", ".join(clouds)
        else:
            clouds_str = "Clear skies"
        
        # Format weather information
        weather = []
        if metar_obj.weather:
            for wx in metar_obj.weather:
                weather.append(str(wx))
            weather_str = ", ".join(weather)
        else:
            weather_str = "No significant weather"
        
        return {
            'raw': raw_metar,
            'decoded': {
                'station': metar_obj.station_id,
                'time': metar_obj.time.strftime('%Y-%m-%d %H:%M UTC'),
                'wind': f"{metar_obj.wind_dir.value():03.0f}° at {metar_obj.wind_speed.value():.0f} kt" + 
                        (f" gusting to {metar_obj.wind_gust.value():.0f} kt" if metar_obj.wind_gust else ""),
                'visibility': f"{metar_obj.vis.value()} meters" if metar_obj.vis else "N/A",
                'weather': weather_str,
                'clouds': clouds_str,
                'temperature': f"{metar_obj.temp.value():.1f}°C",
                'dew_point': f"{metar_obj.dewpt.value():.1f}°C",
                'pressure': f"{metar_obj.press.value():.1f} hPa" if metar_obj.press else "N/A",
                'recent_weather': ', '.join([str(w) for w in metar_obj.recent]) if metar_obj.recent else "N/A",
                'remarks': metar_obj.remarks if metar_obj.remarks else "N/A"
            },
            'timestamp': metar_data[0].get('obsTime', 'N/A')
        }
    except Metar.ParserError as e:
        print(f"Error parsing METAR: {e}")
        return {
            'raw': raw_metar,
            'decoded': None,
            'timestamp': metar_data[0].get('obsTime', 'N/A')
        }

def parse_taf(taf_data):
    """Parse and decode TAF data"""
    if not taf_data or not isinstance(taf_data, list) or len(taf_data) == 0:
        return None
    
    raw_taf = taf_data[0].get('rawTAF', '')
    if not raw_taf:
        return None
    
    return {
        'raw': raw_taf,
        'decoded': parse_taf_forecast(raw_taf),
        'timestamp': taf_data[0].get('issueTime', 'N/A')
    }

def parse_taf_forecast(raw_taf):
    """Improved TAF forecast parser"""
    try:
        taf_obj = Metar.Metar(raw_taf)
        
        weather = []
        if taf_obj.weather:
            for wx in taf_obj.weather:
                weather.append(str(wx))
            weather_str = ", ".join(weather)
        else:
            weather_str = "No significant weather"
        
        clouds = []
        if taf_obj.sky:
            for layer in taf_obj.sky:
                cover = layer[0] if layer[0] else "N/A"
                height = f"{layer[1].value():.0f} ft" if layer[1] else "N/A"
                cloud_type = layer[2] if layer[2] else ""
                clouds.append(f"{cover} at {height} {cloud_type}")
            clouds_str = ", ".join(clouds)
        else:
            clouds_str = "No cloud information"
            
        return {
            'forecast_period': raw_taf.split()[1] + " to " + raw_taf.split()[2] if len(raw_taf.split()) > 2 else "N/A",
            'wind': f"{taf_obj.wind_dir.value():03.0f}° at {taf_obj.wind_speed.value():.0f} kt" if hasattr(taf_obj, 'wind_dir') else "Wind: N/A",
            'visibility': f"{taf_obj.vis.value()} meters" if hasattr(taf_obj, 'vis') and taf_obj.vis else "N/A",
            'weather': weather_str,
            'clouds': clouds_str,
            'raw_forecast': raw_taf
        }
    except Exception as e:
        print(f"Error parsing TAF: {e}")
        parts = raw_taf.split()
        return {
            'forecast_period': " ".join(parts[1:3]) if len(parts) > 3 else "N/A",
            'wind': next((p for p in parts if "KT" in p), "Wind: N/A"),
            'visibility': next((p for p in parts if "SM" in p), "Visibility: N/A"),
            'weather': " ".join([p for p in parts[3:] if "/" not in p and "KT" not in p and "SM" not in p]) or "No significant weather",
            'clouds': "Cloud information not available",
            'raw_forecast': raw_taf
        }

# Update the index route to include coordinates
@app.route('/', methods=['GET', 'POST'])
def index():
    num_stops = 0
    stops = []
    error = None
    map_center = [0, 0]  # Default map center
    
    if request.method == 'POST':
        try:
            num_stops = int(request.form.get('num_stops', 0))
            if num_stops < 1:
                error = "Number of stops must be at least 1"
            else:
                stops = []
                coordinates = []
                for i in range(num_stops):
                    airport_id = request.form.get(f'airport_id_{i}', '').strip().upper()
                    altitude = request.form.get(f'altitude_{i}', '').strip()
                    
                    if len(airport_id) != 4:
                        error = f"Invalid airport code for stop {i+1}"
                        break
                    
                    if not altitude.isdigit():
                        error = f"Invalid altitude for stop {i+1}"
                        break
                    
                    # Get coordinates for this airport
                    lat, lon = get_airport_coordinates(airport_id)
                    coordinates.append((lat, lon))
                    
                    metar_data = fetch_weather_data(airport_id, 'metar')
                    taf_data = fetch_weather_data(airport_id, 'taf')
                    
                    stops.append({
                        'airport_id': airport_id,
                        'altitude': altitude,
                        'latitude': lat,
                        'longitude': lon,
                        'metar': parse_metar(metar_data),
                        'taf': parse_taf(taf_data)
                    })
                
                if coordinates:
                    # Calculate map center as midpoint of all coordinates
                    lats = [c[0] for c in coordinates]
                    lons = [c[1] for c in coordinates]
                    map_center = [sum(lats)/len(lats), sum(lons)/len(lons)]
                
                if not stops and not error:
                    error = "No valid stops entered"
        except ValueError:
            error = "Invalid number of stops entered"
    
    return render_template('index.html', 
                         num_stops=num_stops,
                         stops=stops,
                         error=error,
                         map_center=map_center,
                         current_year=datetime.now().year)


if __name__ == '__main__':
    app.run(debug=True)

if __name__ == '__main__':
    app.run(debug=True)
