import discord
import aiohttp
import asyncio
import json
import time
from typing import Optional, Dict, Any, Union, Tuple
from datetime import datetime, timedelta
from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import humanize_list, box
from redbot.core.utils.predicates import MessagePredicate
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
import logging
from enum import Enum

# Set up logging
log = logging.getLogger("red.weathercog")

class WeatherCache:
    """Simple in-memory cache for weather data"""
    def __init__(self, ttl: int = 600):  # 10 minutes default TTL
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl = ttl
    
    def _is_expired(self, timestamp: float) -> bool:
        return time.time() - timestamp > self.ttl
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if key in self.cache:
            if not self._is_expired(self.cache[key]['timestamp']):
                return self.cache[key]['data']
            else:
                del self.cache[key]
        return None
    
    def set(self, key: str, data: Dict[str, Any]) -> None:
        self.cache[key] = {
            'data': data,
            'timestamp': time.time()
        }
    
    def clear(self) -> None:
        self.cache.clear()

class AQILevel(Enum):
    """Air Quality Index levels and colors"""
    GOOD = (1, "Good", discord.Color.green(), "🟢")
    FAIR = (2, "Fair", discord.Color.yellow(), "🟡") 
    MODERATE = (3, "Moderate", discord.Color.orange(), "🟠")
    POOR = (4, "Poor", discord.Color.red(), "🔴")
    VERY_POOR = (5, "Very Poor", discord.Color.dark_red(), "🟤")
    
    def __init__(self, value, label, color, emoji):
        self.value = value
        self.label = label
        self.color = color
        self.emoji = emoji
    
    @classmethod
    def from_value(cls, value):
        for level in cls:
            if level.value == value:
                return level
        return cls.MODERATE  # Default fallback

class WeatherView(discord.ui.View):
    """Interactive view for weather commands with buttons"""
    def __init__(self, cog, location: str, country_code: str = "us", user_id: int = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.location = location
        self.country_code = country_code
        self.user_id = user_id
        self.current_mode = "current"
    
    @discord.ui.button(label="Current", style=discord.ButtonStyle.primary, emoji="🌤️")
    async def current_weather(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.user_id and interaction.user.id != self.user_id:
            await interaction.response.send_message("You can't interact with this weather display.", ephemeral=True)
            return
        
        self.current_mode = "current"
        embed = await self.cog._get_current_weather_embed(self.location, self.country_code, interaction.user.id)
        if embed:
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Failed to fetch current weather.", ephemeral=True)
    
    @discord.ui.button(label="3-Day", style=discord.ButtonStyle.secondary, emoji="📅")
    async def three_day_forecast(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.user_id and interaction.user.id != self.user_id:
            await interaction.response.send_message("You can't interact with this weather display.", ephemeral=True)
            return
        
        self.current_mode = "3day"
        embed = await self.cog._get_forecast_embed(self.location, self.country_code, 3, interaction.user.id)
        if embed:
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Failed to fetch 3-day forecast.", ephemeral=True)
    
    @discord.ui.button(label="5-Day", style=discord.ButtonStyle.secondary, emoji="📊")
    async def five_day_forecast(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.user_id and interaction.user.id != self.user_id:
            await interaction.response.send_message("You can't interact with this weather display.", ephemeral=True)
            return
        
        self.current_mode = "5day"
        embed = await self.cog._get_forecast_embed(self.location, self.country_code, 5, interaction.user.id)
        if embed:
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Failed to fetch 5-day forecast.", ephemeral=True)
    
    @discord.ui.button(label="7-Day", style=discord.ButtonStyle.secondary, emoji="📈")
    async def seven_day_forecast(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.user_id and interaction.user.id != self.user_id:
            await interaction.response.send_message("You can't interact with this weather display.", ephemeral=True)
            return
        
        self.current_mode = "7day"
        embed = await self.cog._get_forecast_embed(self.location, self.country_code, 7, interaction.user.id)
        if embed:
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Failed to fetch 7-day forecast.", ephemeral=True)
    
    @discord.ui.button(label="Air Quality", style=discord.ButtonStyle.secondary, emoji="🌬️")
    async def air_quality(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.user_id and interaction.user.id != self.user_id:
            await interaction.response.send_message("You can't interact with this weather display.", ephemeral=True)
            return
        
        self.current_mode = "aqi"
        embed = await self.cog._get_air_quality_embed(self.location, self.country_code, interaction.user.id)
        if embed:
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Failed to fetch air quality data.", ephemeral=True)
    
    @discord.ui.button(label="Settings", style=discord.ButtonStyle.success, emoji="⚙️")
    async def settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.user_id and interaction.user.id != self.user_id:
            await interaction.response.send_message("You can't interact with this weather display.", ephemeral=True)
            return
        
        user_config = await self.cog.config.user(interaction.user).all()
        units = user_config.get("units", "imperial")
        temp_unit = "°F" if units == "imperial" else "°C"
        
        embed = discord.Embed(
            title="Weather Settings",
            description=f"Current unit preference: **{units.title()}** ({temp_unit})",
            color=discord.Color.gold()
        )
        embed.add_field(
            name="Change Units",
            value="Use `/weather-settings` to change your unit preferences",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class WeatherCog(commands.Cog):
    """
    Enhanced weather cog with forecasts, air quality, caching, and interactive features.
    
    This cog provides comprehensive weather information including:
    - Current weather conditions
    - Multi-day forecasts (3, 5, 7 days)
    - Air quality index data
    - Interactive Discord UI with buttons
    - User preferences and caching
    - Both slash commands and traditional commands
    """
    
    # Unique identifier for this cog - using a large random number to avoid conflicts
    COG_IDENTIFIER = 260288776360820736
    
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.cache = WeatherCache(ttl=600)  # 10-minute cache
        
        # Configuration schema with detailed defaults
        default_global = {
            "cache_ttl": 600,  # Global cache TTL setting
            "api_calls_today": 0,  # Track API usage
            "last_reset": None  # Last reset timestamp
        }
        
        default_user = {
            "units": "imperial",  # imperial or metric
            "default_location": None,  # User's default location
            "default_country": "us",  # User's default country code
            "show_aqi": True,  # Whether to show AQI in weather displays
            "last_location": None  # Remember last searched location
        }
        
        default_guild = {
            "units": "imperial",  # Server default units
            "cache_ttl": 600,  # Server-specific cache TTL
            "allowed_channels": [],  # Channels where weather commands are allowed
            "disable_buttons": False  # Option to disable interactive buttons
        }
        
        # Initialize Config with force registration and unique identifier
        self.config = Config.get_conf(
            self, 
            identifier=self.COG_IDENTIFIER, 
            force_registration=True
        )
        
        # Register all configuration schemas
        self.config.register_global(**default_global)
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)
        
        # Log successful initialization
        log.info(f"WeatherCog initialized with identifier: {self.COG_IDENTIFIER}")
    
    def cog_unload(self):
        """Clean up resources when cog is unloaded"""
        log.info("WeatherCog unloading - cleaning up resources")
        asyncio.create_task(self.session.close())
        self.cache.clear()
    
    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        """Delete user data for GDPR compliance"""
        await self.config.user_from_id(user_id).clear()
        log.info(f"Deleted user data for user ID: {user_id} (requested by: {requester})")
    
    def _parse_location(self, location: str) -> Tuple[str, str]:
        """Parse location input to determine if it's coordinates, zip, or city name"""
        location = location.strip()
        
        # Check if it's coordinates (lat,lon)
        if ',' in location and all(part.replace('.', '').replace('-', '').isdigit() for part in location.split(',')):
            return "coord", location
        
        # Check if it's a zip code (numbers only or alphanumeric for international)
        if location.replace(' ', '').isalnum() and len(location) <= 10:
            return "zip", location
        
        # Otherwise treat as city name
        return "city", location
    
    def _get_cache_key(self, location: str, country_code: str, endpoint: str) -> str:
        """Generate cache key for weather data"""
        return f"{endpoint}:{location}:{country_code}"
    
    async def _get_api_key(self) -> Optional[str]:
        """Get OpenWeatherMap API key from shared tokens"""
        tokens = await self.bot.get_shared_api_tokens("openweathermap")
        return tokens.get("api_key")
    
    async def _get_user_units(self, user_id: int) -> Tuple[str, str, str]:
        """Get user's preferred units"""
        user_config = await self.config.user_from_id(user_id).all()
        units = user_config.get("units", "imperial")
        temp_unit = "°F" if units == "imperial" else "°C"
        speed_unit = "mph" if units == "imperial" else "m/s"
        return units, temp_unit, speed_unit
    
    async def _make_weather_request(self, endpoint: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Make weather API request with error handling"""
        try:
            async with self.session.get(endpoint, params=params, timeout=10) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 401:
                    log.error("Invalid OpenWeatherMap API key")
                    return {"error": "Invalid API key"}
                elif response.status == 404:
                    return {"error": "Location not found"}
                else:
                    log.error(f"Weather API error: {response.status}")
                    return {"error": f"API error: {response.status}"}
        except asyncio.TimeoutError:
            log.error("Weather API request timed out")
            return {"error": "Request timed out"}
        except Exception as e:
            log.error(f"Weather API request failed: {e}")
            return {"error": str(e)}
    
    async def _get_weather_data(self, location: str, country_code: str, endpoint_type: str, user_id: int) -> Optional[Dict[str, Any]]:
        """Get weather data with caching"""
        api_key = await self._get_api_key()
        if not api_key:
            return {"error": "API key not set"}
        
        # Check cache first
        cache_key = self._get_cache_key(location, country_code, endpoint_type)
        cached_data = self.cache.get(cache_key)
        if cached_data:
            return cached_data
        
        # Determine location type and build parameters
        location_type, parsed_location = self._parse_location(location)
        units, _, _ = await self._get_user_units(user_id)
        
        if endpoint_type == "current":
            base_url = "https://api.openweathermap.org/data/2.5/weather"
        else:
            base_url = "https://api.openweathermap.org/data/2.5/forecast"
        
        params = {"appid": api_key, "units": units}
        
        if location_type == "coord":
            lat, lon = parsed_location.split(',')
            params.update({"lat": lat.strip(), "lon": lon.strip()})
        elif location_type == "zip":
            params["zip"] = f"{parsed_location},{country_code}"
        else:  # city name
            params["q"] = f"{parsed_location},{country_code}"
        
        # Make API request
        data = await self._make_weather_request(base_url, params)
        
        # Cache successful responses
        if data and "error" not in data:
            self.cache.set(cache_key, data)
        
        return data
    
    async def _get_coordinates_from_location(self, location: str, country_code: str) -> Optional[Tuple[float, float]]:
        """Get coordinates from location for AQI API (which requires lat/lon)"""
        location_type, parsed_location = self._parse_location(location)
        
        if location_type == "coord":
            lat, lon = parsed_location.split(',')
            return float(lat.strip()), float(lon.strip())
        
        # For other location types, we need to get coordinates from weather data first
        weather_data = await self._get_weather_data(location, country_code, "current", 0)  # Use user_id 0 for coordinate lookup
        
        if weather_data and "coord" in weather_data:
            return weather_data["coord"]["lat"], weather_data["coord"]["lon"]
        
        return None

    async def _get_air_quality_data(self, location: str, country_code: str, user_id: int) -> Optional[Dict[str, Any]]:
        """Get air quality data from OpenWeatherMap Air Pollution API"""
        api_key = await self._get_api_key()
        if not api_key:
            return {"error": "API key not set"}
        
        # Get coordinates for the location
        coords = await self._get_coordinates_from_location(location, country_code)
        if not coords:
            return {"error": "Could not determine coordinates for location"}
        
        lat, lon = coords
        
        # Check cache first
        cache_key = f"aqi:{lat}:{lon}"
        cached_data = self.cache.get(cache_key)
        if cached_data:
            return cached_data
        
        # Make API request
        base_url = "http://api.openweathermap.org/data/2.5/air_pollution"
        params = {
            "lat": lat,
            "lon": lon,
            "appid": api_key
        }
        
        data = await self._make_weather_request(base_url, params)
        
        # Cache successful responses
        if data and "error" not in data:
            self.cache.set(cache_key, data)
        
        return data

    async def _get_air_quality_forecast_data(self, location: str, country_code: str, user_id: int) -> Optional[Dict[str, Any]]:
        """Get air quality forecast data"""
        api_key = await self._get_api_key()
        if not api_key:
            return {"error": "API key not set"}
        
        coords = await self._get_coordinates_from_location(location, country_code)
        if not coords:
            return {"error": "Could not determine coordinates for location"}
        
        lat, lon = coords
        
        # Check cache first
        cache_key = f"aqi_forecast:{lat}:{lon}"
        cached_data = self.cache.get(cache_key)
        if cached_data:
            return cached_data
        
        # Make API request
        base_url = "http://api.openweathermap.org/data/2.5/air_pollution/forecast"
        params = {
            "lat": lat,
            "lon": lon,
            "appid": api_key
        }
        
        data = await self._make_weather_request(base_url, params)
        
        # Cache successful responses
        if data and "error" not in data:
            self.cache.set(cache_key, data)
        
        return data

    async def _get_air_quality_embed(self, location: str, country_code: str, user_id: int) -> Optional[discord.Embed]:
        """Create embed for air quality information"""
        # Get both current and forecast data
        current_data = await self._get_air_quality_data(location, country_code, user_id)
        forecast_data = await self._get_air_quality_forecast_data(location, country_code, user_id)
        
        if not current_data or "error" in current_data:
            return None
        
        # Get location name from weather data
        weather_data = await self._get_weather_data(location, country_code, "current", user_id)
        if weather_data and "name" in weather_data:
            city_name = weather_data["name"]
            country = weather_data["sys"]["country"]
        else:
            city_name = location
            country = country_code.upper()
        
        # Current AQI data
        current_aqi = current_data["list"][0]
        aqi_value = current_aqi["main"]["aqi"]
        aqi_level = AQILevel.from_value(aqi_value)
        
        # Components data
        components = current_aqi["components"]
        
        embed = discord.Embed(
            title=f"🌬️ Air Quality in {city_name}, {country}",
            description=f"{aqi_level.emoji} **{aqi_level.label}** (AQI: {aqi_value}/5)",
            color=aqi_level.color,
            timestamp=datetime.utcnow()
        )
        
        # Main pollutants
        embed.add_field(
            name="🏭 Main Pollutants",
            value=(
                f"PM2.5: {components.get('pm2_5', 0):.1f} μg/m³\n"
                f"PM10: {components.get('pm10', 0):.1f} μg/m³\n"
                f"O₃: {components.get('o3', 0):.1f} μg/m³"
            ),
            inline=True
        )
        
        # Other pollutants
        embed.add_field(
            name="🧪 Other Pollutants",
            value=(
                f"NO₂: {components.get('no2', 0):.1f} μg/m³\n"
                f"SO₂: {components.get('so2', 0):.1f} μg/m³\n"
                f"CO: {components.get('co', 0):.0f} μg/m³"
            ),
            inline=True
        )
        
        # Health recommendations
        health_advice = {
            1: "Air quality is satisfactory. Enjoy outdoor activities!",
            2: "Air quality is acceptable for most people.",
            3: "Sensitive individuals should consider limiting outdoor activities.",
            4: "Everyone should limit outdoor activities, especially sensitive groups.",
            5: "Avoid outdoor activities. Health warnings for everyone."
        }
        
        embed.add_field(
            name="💡 Health Advice",
            value=health_advice.get(aqi_value, "Monitor air quality conditions."),
            inline=False
        )
        
        # Add forecast if available
        if forecast_data and "list" in forecast_data:
            forecast_text = ""
            forecast_list = forecast_data["list"][:24]  # Next 24 hours
            
            # Group by day
            daily_forecasts = {}
            for entry in forecast_list:
                dt_object = datetime.fromtimestamp(entry["dt"])
                date_str = dt_object.strftime("%Y-%m-%d")
                
                if date_str not in daily_forecasts:
                    daily_forecasts[date_str] = []
                daily_forecasts[date_str].append(entry["main"]["aqi"])
            
            # Show next 3 days
            for i, (date_str, aqi_values) in enumerate(list(daily_forecasts.items())[:3]):
                if i == 0:
                    day_name = "Today"
                elif i == 1:
                    day_name = "Tomorrow"
                else:
                    day_name = datetime.strptime(date_str, "%Y-%m-%d").strftime("%a")
                
                avg_aqi = sum(aqi_values) / len(aqi_values)
                forecast_level = AQILevel.from_value(round(avg_aqi))
                forecast_text += f"{day_name}: {forecast_level.emoji} {forecast_level.label}\n"
            
            if forecast_text:
                embed.add_field(
                    name="📅 3-Day Forecast",
                    value=forecast_text.strip(),
                    inline=False
                )
    
        # AQI scale reference
        embed.add_field(
            name="📊 AQI Scale",
            value=(
                "🟢 1: Good\n🟡 2: Fair\n🟠 3: Moderate\n"
                "🔴 4: Poor\n🟤 5: Very Poor"
            ),
            inline=True
        )
        
        embed.set_footer(text="Powered by OpenWeatherMap Air Pollution API")
        
        return embed
    
    async def _get_current_weather_embed(self, location: str, country_code: str, user_id: int) -> Optional[discord.Embed]:
        """Create embed for current weather"""
        data = await self._get_weather_data(location, country_code, "current", user_id)
        
        if not data or "error" in data:
            return None
        
        units, temp_unit, speed_unit = await self._get_user_units(user_id)
        
        city_name = data["name"]
        country = data["sys"]["country"]
        weather_desc = data["weather"][0]["description"].title()
        temp = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        humidity = data["main"]["humidity"]
        pressure = data["main"]["pressure"]
        wind_speed = data["wind"]["speed"]
        wind_deg = data["wind"].get("deg", 0)
        visibility = data.get("visibility", 0) / 1000  # Convert to km
        
        # Wind direction
        wind_directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        wind_dir = wind_directions[int((wind_deg + 11.25) / 22.5) % 16]
        
        embed = discord.Embed(
            title=f"🌤️ Current Weather in {city_name}, {country}",
            description=f"**{weather_desc}**",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="🌡️ Temperature",
            value=f"{temp:.1f}{temp_unit}\nFeels like {feels_like:.1f}{temp_unit}",
            inline=True
        )
        
        embed.add_field(
            name="💧 Humidity",
            value=f"{humidity}%",
            inline=True
        )
        
        embed.add_field(
            name="🌬️ Wind",
            value=f"{wind_speed:.1f} {speed_unit} {wind_dir}",
            inline=True
        )
        
        embed.add_field(
            name="🔽 Pressure",
            value=f"{pressure} hPa",
            inline=True
        )
        
        embed.add_field(
            name="👁️ Visibility",
            value=f"{visibility:.1f} km",
            inline=True
        )
        
        # Add sunrise/sunset if available
        if "sys" in data and "sunrise" in data["sys"]:
            sunrise = datetime.fromtimestamp(data["sys"]["sunrise"]).strftime("%H:%M")
            sunset = datetime.fromtimestamp(data["sys"]["sunset"]).strftime("%H:%M")
            embed.add_field(
                name="🌅 Sun Times",
                value=f"Rise: {sunrise}\nSet: {sunset}",
                inline=True
            )
        
        # Add basic AQI info to current weather if user preference allows
        user_config = await self.config.user_from_id(user_id).all()
        if user_config.get("show_aqi", True):
            try:
                aqi_data = await self._get_air_quality_data(location, country_code, user_id)
                if aqi_data and "error" not in aqi_data:
                    aqi_value = aqi_data["list"][0]["main"]["aqi"]
                    aqi_level = AQILevel.from_value(aqi_value)
                    embed.add_field(
                        name="🌬️ Air Quality",
                        value=f"{aqi_level.emoji} {aqi_level.label} ({aqi_value}/5)",
                        inline=True
                    )
            except Exception:
                pass  # Don't fail weather display if AQI fails
        
        embed.set_thumbnail(url=f"http://openweathermap.org/img/wn/{data['weather'][0]['icon']}@2x.png")
        embed.set_footer(text="Powered by OpenWeatherMap")
        
        return embed
    
    async def _get_forecast_embed(self, location: str, country_code: str, days: int, user_id: int) -> Optional[discord.Embed]:
        """Create embed for weather forecast"""
        data = await self._get_weather_data(location, country_code, "forecast", user_id)
        
        if not data or "error" in data:
            return None
        
        units, temp_unit, speed_unit = await self._get_user_units(user_id)
        
        city_name = data["city"]["name"]
        country = data["city"]["country"]
        
        embed = discord.Embed(
            title=f"📅 {days}-Day Weather Forecast for {city_name}, {country}",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        # Process forecast data
        forecast_list = data["list"]
        daily_forecasts = {}
        
        for entry in forecast_list:
            dt_object = datetime.fromtimestamp(entry["dt"])
            date_str = dt_object.strftime("%Y-%m-%d")
            
            if date_str not in daily_forecasts:
                daily_forecasts[date_str] = {
                    "temp_min": entry["main"]["temp_min"],
                    "temp_max": entry["main"]["temp_max"],
                    "description": entry["weather"][0]["description"].title(),
                    "icon": entry["weather"][0]["icon"],
                    "humidity": entry["main"]["humidity"],
                    "wind_speed": entry["wind"]["speed"],
                    "date": dt_object.strftime("%a, %b %d"),
                    "entries": [entry]
                }
            else:
                daily_forecasts[date_str]["temp_min"] = min(daily_forecasts[date_str]["temp_min"], entry["main"]["temp_min"])
                daily_forecasts[date_str]["temp_max"] = max(daily_forecasts[date_str]["temp_max"], entry["main"]["temp_max"])
                daily_forecasts[date_str]["entries"].append(entry)
        
        # Add forecast fields for requested days
        sorted_dates = sorted(daily_forecasts.keys())[:days]
        
        for i, date_key in enumerate(sorted_dates):
            forecast = daily_forecasts[date_key]
            
            # Calculate average humidity and wind speed for the day
            avg_humidity = sum(entry["main"]["humidity"] for entry in forecast["entries"]) / len(forecast["entries"])
            avg_wind = sum(entry["wind"]["speed"] for entry in forecast["entries"]) / len(forecast["entries"])
            
            field_value = (
                f"🌡️ {forecast['temp_min']:.0f}{temp_unit} - {forecast['temp_max']:.0f}{temp_unit}\n"
                f"🌤️ {forecast['description']}\n"
                f"💧 {avg_humidity:.0f}% humidity\n"
                f"🌬️ {avg_wind:.1f} {speed_unit} wind"
            )
            
            embed.add_field(
                name=f"{forecast['date']} {'(Today)' if i == 0 else ''}",
                value=field_value,
                inline=True
            )
        
        embed.set_footer(text="Powered by OpenWeatherMap | Tap buttons to switch views")
        
        return embed
    
    # Slash Commands
    @discord.app_commands.command(name="weather", description="Get weather information for a location")
    @discord.app_commands.describe(
        location="Location (city name, ZIP code, or coordinates)",
        country="Country code (default: us)",
        forecast="Forecast days (1, 3, 5, or 7)"
    )
    async def weather_slash(
        self, 
        interaction: discord.Interaction, 
        location: str, 
        country: str = "us",
        forecast: Optional[int] = None
    ):
        """Slash command for weather"""
        await interaction.response.defer()
        
        try:
            if forecast and forecast in [3, 5, 7]:
                embed = await self._get_forecast_embed(location, country, forecast, interaction.user.id)
            else:
                embed = await self._get_current_weather_embed(location, country, interaction.user.id)
            
            if embed:
                view = WeatherView(self, location, country, interaction.user.id)
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send("❌ Could not fetch weather data. Please check your location and try again.")
        
        except Exception as e:
            log.error(f"Weather slash command error: {e}")
            await interaction.followup.send("❌ An error occurred while fetching weather data.")
    
    @discord.app_commands.command(name="weather-settings", description="Configure your weather preferences")
    @discord.app_commands.describe(units="Temperature units (imperial or metric)")
    @discord.app_commands.choices(units=[
        discord.app_commands.Choice(name="Imperial (°F, mph)", value="imperial"),
        discord.app_commands.Choice(name="Metric (°C, m/s)", value="metric")
    ])
    async def weather_settings_slash(self, interaction: discord.Interaction, units: str):
        """Slash command for weather settings"""
        await self.config.user(interaction.user).units.set(units)
        
        temp_unit = "°F" if units == "imperial" else "°C"
        speed_unit = "mph" if units == "imperial" else "m/s"
        
        embed = discord.Embed(
            title="⚙️ Weather Settings Updated",
            description=f"Your unit preference has been set to **{units.title()}**",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Units",
            value=f"Temperature: {temp_unit}\nWind Speed: {speed_unit}",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.app_commands.command(name="air-quality", description="Get air quality information for a location")
    @discord.app_commands.describe(
        location="Location (city name, ZIP code, or coordinates)",
        country="Country code (default: us)"
    )
    async def air_quality_slash(
        self, 
        interaction: discord.Interaction, 
        location: str, 
        country: str = "us"
    ):
        """Slash command for air quality"""
        await interaction.response.defer()
        
        try:
            embed = await self._get_air_quality_embed(location, country, interaction.user.id)
        
            if embed:
                view = WeatherView(self, location, country, interaction.user.id)
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send("❌ Could not fetch air quality data. Please check your location and try again.")
    
        except Exception as e:
            log.error(f"Air quality slash command error: {e}")
            await interaction.followup.send("❌ An error occurred while fetching air quality data.")
    
    # Traditional Commands (keeping for compatibility)
    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def weather(self, ctx, location: str, country_code: str = "us", days: Optional[int] = None):
        """Get weather information for a location
        
        Usage:
        [p]weather <location> [country_code] [days]
        
        Examples:
        [p]weather "New York"
        [p]weather 90210 us
        [p]weather "London" gb 5
        [p]weather 40.7128,-74.0060  (coordinates)
        """
        async with ctx.typing():
            try:
                if days and days in [3, 5, 7]:
                    embed = await self._get_forecast_embed(location, country_code, days, ctx.author.id)
                else:
                    embed = await self._get_current_weather_embed(location, country_code, ctx.author.id)
                
                if embed:
                    view = WeatherView(self, location, country_code, ctx.author.id)
                    await ctx.send(embed=embed, view=view)
                else:
                    await ctx.send("❌ Could not fetch weather data. Please check your location and try again.")
            
            except Exception as e:
                log.error(f"Weather command error: {e}")
                await ctx.send("❌ An error occurred while fetching weather data.")
    
    @weather.command(name="settings")
    async def weather_settings(self, ctx, units: str = None):
        """Configure your weather preferences
        
        Usage: [p]weather settings [imperial|metric]
        """
        if units is None:
            user_config = await self.config.user(ctx.author).all()
            current_units = user_config.get("units", "imperial")
            temp_unit = "°F" if current_units == "imperial" else "°C"
            
            embed = discord.Embed(
                title="⚙️ Your Weather Settings",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Current Units",
                value=f"{current_units.title()} ({temp_unit})",
                inline=False
            )
            embed.add_field(
                name="Change Units",
                value=f"`{ctx.prefix}weather settings imperial` or `{ctx.prefix}weather settings metric`",
                inline=False
            )
            
            await ctx.send(embed=embed)
            return
        
        if units.lower() not in ["imperial", "metric"]:
            await ctx.send("❌ Units must be either 'imperial' or 'metric'.")
            return
        
        await self.config.user(ctx.author).units.set(units.lower())
        
        temp_unit = "°F" if units.lower() == "imperial" else "°C"
        speed_unit = "mph" if units.lower() == "imperial" else "m/s"
        
        embed = discord.Embed(
            title="✅ Settings Updated",
            description=f"Your unit preference has been set to **{units.title()}**",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Units",
            value=f"Temperature: {temp_unit}\nWind Speed: {speed_unit}",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @weather.command(name="info")
    async def weather_info(self, ctx):
        """Display information about the WeatherCog"""
        embed = discord.Embed(
            title="🌤️ Enhanced WeatherCog Information",
            description="Advanced weather information with forecasts, caching, and interactive features",
            color=discord.Color.teal()
        )
        
        embed.add_field(
            name="📍 Location Support",
            value="• City names\n• ZIP/Postal codes\n• Coordinates (lat,lon)",
            inline=True
        )
        
        embed.add_field(
            name="📅 Forecast Options",
            value="• Current weather\n• 3, 5, 7-day forecasts\n• Interactive buttons",
            inline=True
        )
        
        embed.add_field(
            name="⚙️ Features",
            value="• User preferences\n• Smart caching\n• Slash commands\n• Enhanced embeds\n• Air quality data",
            inline=True
        )
        
        embed.add_field(
            name="🔧 Commands",
            value=f"`{ctx.prefix}weather <location>`\n`/weather <location>`\n`{ctx.prefix}weather aqi <location>`\n`/air-quality <location>`\n`{ctx.prefix}weather settings`",
            inline=False
        )
        
        embed.add_field(
            name="🔧 Configuration",
            value=f"Cog ID: `{self.COG_IDENTIFIER}`\nForce Registration: ✅",
            inline=False
        )
        
        embed.set_footer(text="Powered by OpenWeatherMap API")
        
        await ctx.send(embed=embed)
    
    @weather.command(name="aqi", aliases=["airquality", "air"])
    async def air_quality_command(self, ctx, location: str, country_code: str = "us"):
        """Get air quality information for a location
    
        Usage: [p]weather aqi <location> [country_code]
    
        Examples:
        [p]weather aqi "New York"
        [p]weather aqi 90210 us
        [p]weather aqi 40.7128,-74.0060
        """
        async with ctx.typing():
            try:
                embed = await self._get_air_quality_embed(location, country_code, ctx.author.id)
            
                if embed:
                    view = WeatherView(self, location, country_code, ctx.author.id)
                    await ctx.send(embed=embed, view=view)
                else:
                    await ctx.send("❌ Could not fetch air quality data. Please check your location and try again.")
        
            except Exception as e:
                log.error(f"Air quality command error: {e}")
                await ctx.send("❌ An error occurred while fetching air quality data.")
    
    # Admin Commands
    @commands.group()
    @commands.is_owner()
    async def weatherset(self, ctx):
        """Weather cog configuration commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
    
    @weatherset.command()
    async def setapikey(self, ctx, api_key: str):
        """Set the OpenWeatherMap API key"""
        await self.bot.set_shared_api_tokens("openweathermap", api_key=api_key)
        await ctx.send("✅ OpenWeatherMap API key has been set successfully!")
    
    @weatherset.command()
    async def viewapikey(self, ctx):
        """View the current API key (sent via DM)"""
        tokens = await self.bot.get_shared_api_tokens("openweathermap")
        api_key = tokens.get("api_key")
        
        if api_key:
            try:
                await ctx.author.send(f"Current OpenWeatherMap API key: `{api_key}`")
                await ctx.send("✅ API key sent to your DMs.")
            except discord.Forbidden:
                await ctx.send("❌ Could not send DM. Please check your privacy settings.")
        else:
            await ctx.send("❌ No API key is currently set.")
    
    @weatherset.command()
    async def clearcache(self, ctx):
        """Clear the weather data cache"""
        self.cache.clear()
        await ctx.send("✅ Weather cache has been cleared.")
    
    @weatherset.command()
    async def cachestats(self, ctx):
        """View cache statistics"""
        cache_size = len(self.cache.cache)
        embed = discord.Embed(
            title="📊 Cache Statistics",
            color=discord.Color.blue()
        )
        embed.add_field(name="Cached Entries", value=str(cache_size), inline=True)
        embed.add_field(name="TTL", value=f"{self.cache.ttl} seconds", inline=True)
        embed.add_field(name="Cog ID", value=str(self.COG_IDENTIFIER), inline=True)
        
        await ctx.send(embed=embed)
    
    @weatherset.command()
    async def configinfo(self, ctx):
        """Display configuration information"""
        global_config = await self.config.all()
        
        embed = discord.Embed(
            title="🔧 WeatherCog Configuration",
            color=discord.Color.gold()
        )
        embed.add_field(
            name="Unique Identifier",
            value=f"`{self.COG_IDENTIFIER}`",
            inline=False
        )
        embed.add_field(
            name="Force Registration",
            value="✅ Enabled",
            inline=True
        )
        embed.add_field(
            name="Cache TTL",
            value=f"{global_config.get('cache_ttl', 600)} seconds",
            inline=True
        )
        embed.add_field(
            name="Registration Status",
            value="✅ Successfully Registered",
            inline=True
        )
        
        await ctx.send(embed=embed)

async def setup(bot):
    cog = WeatherCog(bot)
    await bot.add_cog(cog)