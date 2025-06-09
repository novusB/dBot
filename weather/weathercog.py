import discord
import aiohttp # For making asynchronous HTTP requests
import asyncio # For handling asynchronous operations
from redbot.core import commands, Config # Import commands framework and Config for settings
from redbot.core.utils.chat_formatting import humanize_list # For formatting lists nicely
from datetime import datetime, timedelta # For handling dates and times

class WeatherCog(commands.Cog):
    """
    A custom cog for Red Discord Bot to fetch current weather by ZIP code and air quality.
    This cog uses Red's shared API tokens for enhanced security.
    """

    # We no longer store the API key directly in _config_schema.
    # It will be managed via Red's shared API tokens.
    _config_schema = {} 

    def __init__(self, bot):
        """
        Constructor for the WeatherCog.
        Args:
            bot: The Red bot instance.
        """
        self.bot = bot
        # Initialize the Config object for this cog.
        # The unique identifier 'weathercog' ensures settings are separate from other cogs.
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        # Register the default configuration schema (now empty as API key is shared).
        self.config.register_global(**self._config_schema)
        # Initialize an aiohttp ClientSession for making web requests.
        # This session is created once and reused for efficiency.
        self.session = aiohttp.ClientSession()

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        """
        No data to delete for a user. This cog does not store user-specific data.
        Required by Red for data privacy compliance.
        """
        return

    def cog_unload(self):
        """
        Called when the cog is unloaded.
        Cleans up the aiohttp ClientSession to prevent resource leaks.
        """
        # Ensure the aiohttp session is closed when the cog is unloaded.
        # This prevents lingering connections.
        asyncio.create_task(self.session.close())

    @commands.group()
    @commands.is_owner() # Only the bot owner can use these commands
    async def weatherset(self, ctx):
        """
        Commands for configuring the WeatherCog.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @weatherset.command()
    async def setapikey(self, ctx, api_key: str):
        """
        Sets the OpenWeatherMap API key using Red's shared API tokens.
        You can get an API key from: https://openweathermap.org/api
        
        Note: It might take a few minutes (or occasionally longer) for a new API key to become active on OpenWeatherMap's side.
        
        This command will store the key using Red's `set api` command internally.
        For future reference, you can also use `[p]set api openweathermap api_key <your_api_key_here>` directly.

        Usage: [p]weatherset setapikey <your_api_key_here>
        """
        # Store the API key using Red's shared API tokens
        await self.bot.set_shared_api_tokens("openweathermap", api_key=api_key) 
        await ctx.send(
            "OpenWeatherMap API key has been set and stored securely using Red's shared API tokens.\n"
            f"You can also manage this key directly with `{ctx.clean_prefix}set api openweathermap api_key <your_key>`."
        )

    @weatherset.command()
    async def viewapikey(self, ctx):
        """
        Views the currently stored OpenWeatherMap API key (from Red's shared API tokens).
        This command is only usable by the bot owner.
        """
        # Retrieve the API key from Red's shared API tokens
        tokens = await self.bot.get_shared_api_tokens("openweathermap")
        api_key = tokens.get("api_key")

        if api_key:
            try:
                await ctx.author.send(f"The current OpenWeatherMap API key is: `{api_key}`")
                if ctx.guild: # Send a public confirmation if used in a guild
                    await ctx.send("The API key has been sent to your DMs.")
            except discord.Forbidden:
                await ctx.send(
                    "I could not send the API key to your DMs. "
                    "Please check your Discord privacy settings to allow DMs from this bot."
                )
            except Exception as e:
                await ctx.send(f"An unexpected error occurred while sending the API key to your Dbot DMs: {e}")
                self.bot.logger.error(f"WeatherCog viewapikey error: {e}")
        else:
            await ctx.send(
                f"No OpenWeatherMap API key is currently set. "
                f"Please set it using `{ctx.clean_prefix}set api openweathermap api_key <your_key>`."
            )

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 60, commands.BucketType.user) # Cooldown changed to 60 seconds
    async def weather(self, ctx, zip_code: str, country_code: str = "us", days: int = None):
        """
        Gets the current weather conditions or a 1-day forecast for a given ZIP code.

        Usage:
        [p]weather <zip_code> [country_code]
        [p]weather <zip_code> [country_code] <days_for_forecast>

        To get the current weather:
        [p]weather <zip_code>
        [p]weather <zip_code> <country_code>
        (If you provide a number other than '1' for days_for_forecast,
         it will default to showing the current weather.)

        To get a 1-day forecast:
        [p]weather <zip_code> 1
        [p]weather <zip_code> <country_code> 1

        Examples:
        [p]weather 90210                 - Current weather for Beverly Hills, USA
        [p]weather 78701 us             - Current weather for Austin, Texas, USA
        [p]weather SW1A0AA gb 1         - 1-day forecast for London, UK
        [p]weather 90210 1              - 1-day forecast for Beverly Hills, USA
        [p]weather 78701 7              - Will show current weather for Austin, Texas, USA
        """
        # Retrieve the API key from Red's shared API tokens
        tokens = await self.bot.get_shared_api_tokens("openweathermap")
        api_key = tokens.get("api_key")

        if not api_key:
            return await ctx.send(
                f"The OpenWeatherMap API key is not set. Please set it using Red's shared API tokens:\n"
                f"`{ctx.clean_prefix}set api openweathermap api_key <your_api_key>`."
            )

        if not zip_code.isalnum():
            return await ctx.send("Please provide a valid ZIP/postal code.")

        units = "imperial" # Default to Fahrenheit for US, can be made configurable
        temp_unit = "°F" if units == "imperial" else "°C"
        speed_unit = "mph" if units == "imperial" else "m/s"

        # If days is 1, fetch 1-day forecast; otherwise, fetch current weather
        if days == 1: # Fetch 1-day forecast
            base_url = "https://api.openweathermap.org/data/2.5/forecast"
            params = {
                "zip": f"{zip_code},{country_code}",
                "appid": api_key,
                "units": units
            }

            try:
                async with self.session.get(base_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        city_name = data["city"]["name"]
                        
                        embed = discord.Embed(
                            title=f"Weather Forecast for {city_name} (1 Day)",
                            color=discord.Color.green() # Different color for forecast
                        )
                        embed.set_footer(text="Powered by OpenWeatherMap | Daily summaries from 3-hour step forecast")

                        # Process the 5-day / 3-hour forecast data to get daily summaries
                        forecast_list = data["list"]
                        
                        # Dictionary to hold one entry per day
                        daily_forecasts = {}

                        for entry in forecast_list:
                            dt_object = datetime.fromtimestamp(entry["dt"])
                            # Get the date part (YYYY-MM-DD)
                            date_str = dt_object.strftime("%Y-%m-%d")

                            if date_str not in daily_forecasts:
                                daily_forecasts[date_str] = {
                                    "temp_min": entry["main"]["temp_min"],
                                    "temp_max": entry["main"]["temp_max"],
                                    "description": entry["weather"][0]["description"].capitalize(),
                                    "icon": entry["weather"][0]["icon"],
                                    "date": dt_object.strftime("%a, %b %d") # E.g., Mon, Jun 09
                                }
                            else:
                                daily_forecasts[date_str]["temp_min"] = min(daily_forecasts[date_str]["temp_min"], entry["main"]["temp_min"])
                                daily_forecasts[date_str]["temp_max"] = max(daily_forecasts[date_str]["temp_max"], entry["main"]["temp_max"])

                        # Add fields for only the first day
                        first_day_key = sorted(daily_forecasts.keys())[0]
                        forecast = daily_forecasts[first_day_key]
                        embed.add_field(
                            name=forecast["date"],
                            value=(
                                f"Temp: {forecast['temp_min']:.0f}{temp_unit} - {forecast['temp_max']:.0f}{temp_unit}\n"
                                f"Condition: {forecast['description']}"
                            ),
                            inline=False
                        )
                            
                        await ctx.send(embed=embed)

                    elif response.status == 401:
                        await ctx.send(f"Error: Invalid OpenWeatherMap API key. Please check your key set with `{ctx.clean_prefix}set api openweathermap api_key <your_key>`.")
                    elif response.status == 404:
                        await ctx.send("Error: ZIP/postal code or country not found for forecast. Please check your input.")
                    else:
                        await ctx.send(f"An unexpected error occurred with the weather API (Status: {response.status}).")
            except aiohttp.ClientConnectorError:
                await ctx.send("Could not connect to the weather API for forecast. Please try again later.")
            except asyncio.TimeoutError:
                await ctx.send("The weather API forecast request timed out. Please try again later.")
            except Exception as e:
                await ctx.send(f"An error occurred during forecast lookup: {e}")
                self.bot.logger.error(f"WeatherCog error (forecast): {e}")

        else: # Fetch current weather (if days is None or any number other than 1)
            base_url = "https://api.openweathermap.org/data/2.5/weather"
            params = {
                "zip": f"{zip_code},{country_code}",
                "appid": api_key,
                "units": units
            }
            try:
                async with self.session.get(base_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        city_name = data["name"]
                        weather_description = data["weather"][0]["description"].capitalize()
                        temperature = data["main"]["temp"]
                        feels_like = data["main"]["feels_like"]
                        humidity = data["main"]["humidity"]
                        wind_speed = data["wind"]["speed"]
                        
                        embed = discord.Embed(
                            title=f"Current Weather in {city_name}",
                            description=f"**{weather_description}**",
                            color=discord.Color.blue()
                        )
                        embed.add_field(name="Temperature", value=f"{temperature}{temp_unit} (Feels like {feels_like}{temp_unit})", inline=False)
                        embed.add_field(name="Humidity", value=f"{humidity}%", inline=True)
                        embed.add_field(name="Wind Speed", value=f"{wind_speed} {speed_unit}", inline=True)
                        embed.set_footer(text="Powered by OpenWeatherMap")
                        embed.set_thumbnail(url=f"http://openweathermap.org/img/wn/{data['weather'][0]['icon']}@2x.png")
                        await ctx.send(embed=embed)
                    elif response.status == 401:
                        await ctx.send(f"Error: Invalid OpenWeatherMap API key. Please check your key set with `{ctx.clean_prefix}set api openweathermap api_key <your_key>`.")
                    elif response.status == 404:
                        await ctx.send("Error: ZIP/postal code or country not found. Please check your input.")
                    else:
                        await ctx.send(f"An unexpected error occurred with the weather API (Status: {response.status}).")
            except aiohttp.ClientConnectorError:
                await ctx.send("Could not connect to the weather API. Please try again later.")
            except asyncio.TimeoutError:
                await ctx.send("The weather API request timed out. Please try again later.")
            except Exception as e:
                await ctx.send(f"An error occurred: {e}")
                self.bot.logger.error(f"WeatherCog error (current weather): {e}")

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 60, commands.BucketType.user) # Cooldown changed to 60 seconds
    async def aqi(self, ctx, zip_code: str, country_code: str = "us"):
        """
        Gets the current Air Quality Index (AQI) and pollutant concentrations for a given ZIP code.

        Usage:
        [p]aqi <zip_code> [country_code]

        Examples:
        [p]aqi 90210
        [p]aqi 78701 us
        [p]aqi SW1A0AA gb
        """
        tokens = await self.bot.get_shared_api_tokens("openweathermap")
        api_key = tokens.get("api_key")

        if not api_key:
            return await ctx.send(
                f"The OpenWeatherMap API key is not set. Please set it using Red's shared API tokens:\n"
                f"`{ctx.clean_prefix}set api openweathermap api_key <your_api_key>`."
            )

        if not zip_code.isalnum():
            return await ctx.send("Please provide a valid ZIP/postal code.")

        # --- Step 1: Get Latitude and Longitude from ZIP code using Geocoding API ---
        geo_url = "http://api.openweathermap.org/geo/1.0/zip"
        geo_params = {
            "zip": f"{zip_code},{country_code}",
            "appid": api_key
        }

        lat, lon, city_name = None, None, None

        try:
            async with self.session.get(geo_url, params=geo_params) as geo_response:
                if geo_response.status == 200:
                    geo_data = await geo_response.json()
                    lat = geo_data.get("lat")
                    lon = geo_data.get("lon")
                    city_name = geo_data.get("name")
                    if not lat or not lon or not city_name:
                        return await ctx.send("Could not find coordinates for the provided ZIP/postal code and country. Please try again.")
                elif geo_response.status == 401:
                    return await ctx.send(f"Error: Invalid OpenWeatherMap API key. Please check your key set with `{ctx.clean_prefix}set api openweathermap api_key <your_key>`.")
                elif geo_response.status == 404:
                    return await ctx.send("Error: ZIP/postal code or country not found for geocoding. Please check your input.")
                else:
                    return await ctx.send(f"An unexpected error occurred with the geocoding API (Status: {geo_response.status}).")
        except aiohttp.ClientConnectorError:
            return await ctx.send("Could not connect to the geocoding API. Please try again later.")
        except asyncio.TimeoutError:
            return await ctx.send("The geocoding API request timed out. Please try again later.")
        except Exception as e:
            self.bot.logger.error(f"WeatherCog AQI geocoding error: {e}")
            return await ctx.send(f"An error occurred during geocoding for AQI: {e}")

        # --- Step 2: Get Air Quality Data using Lat/Lon ---
        aq_url = "http://api.openweathermap.org/data/2.5/air_pollution"
        aq_params = {
            "lat": lat,
            "lon": lon,
            "appid": api_key
        }

        # Mapping AQI value to qualitative description
        aqi_descriptions = {
            1: "Good",
            2: "Fair",
            3: "Moderate",
            4: "Poor",
            5: "Very Poor"
        }

        try:
            async with self.session.get(aq_url, params=aq_params) as aq_response:
                if aq_response.status == 200:
                    aq_data = await aq_response.json()
                    
                    # OpenWeatherMap's Air Pollution API returns a 'list' where the first item is current data
                    if not aq_data.get("list"):
                        return await ctx.send(f"No air quality data available for {city_name} at this time.")

                    current_aq = aq_data["list"][0]
                    aqi_value = current_aq["main"]["aqi"]
                    components = current_aq["components"]
                    
                    aqi_text = aqi_descriptions.get(aqi_value, "Unknown")
                    
                    embed = discord.Embed(
                        title=f"Air Quality in {city_name}",
                        description=f"**AQI: {aqi_value} ({aqi_text})**",
                        color=discord.Color.dark_purple() # Different color for AQI
                    )
                    embed.set_footer(text="Powered by OpenWeatherMap Air Pollution API")

                    # Add pollutant concentrations
                    pollutants = {
                        "CO": "Carbon Monoxide",
                        "NO": "Nitrogen Monoxide",
                        "NO2": "Nitrogen Dioxide",
                        "O3": "Ozone",
                        "SO2": "Sulphur Dioxide",
                        "PM2_5": "Fine Particulates (PM2.5)",
                        "PM10": "Coarse Particulates (PM10)",
                        "NH3": "Ammonia"
                    }
                    
                    for abbr, full_name in pollutants.items():
                        # OpenWeatherMap uses 'pm2_5' but our dict has 'PM2_5', so convert
                        component_key = abbr.lower() if abbr in ["PM2_5", "PM10"] else abbr.lower() 
                        # Special handling for PM2.5 and PM10 to match API response keys if needed
                        if abbr == "PM2_5": component_key = "pm2_5"
                        if abbr == "PM10": component_key = "pm10"

                        value = components.get(component_key)
                        if value is not None:
                            embed.add_field(name=full_name, value=f"{value:.2f} μg/m³", inline=True)

                    await ctx.send(embed=embed)

                elif aq_response.status == 401:
                    await ctx.send(f"Error: Invalid OpenWeatherMap API key. Please check your key set with `{ctx.clean_prefix}set api openweathermap api_key <your_key>`.")
                elif aq_response.status == 404: # This might happen if no AQ data for precise lat/lon
                    await ctx.send(f"No air quality data found for {city_name}. It's possible there are no monitoring stations in this specific area.")
                else:
                    await ctx.send(f"An unexpected error occurred with the air quality API (Status: {aq_response.status}).")
        except aiohttp.ClientConnectorError:
            await ctx.send("Could not connect to the air quality API. Please try again later.")
        except asyncio.TimeoutError:
            await ctx.send("The air quality API request timed out. Please try again later.")
        except Exception as e:
            self.bot.logger.error(f"WeatherCog AQI lookup error: {e}")
            await ctx.send(f"An error occurred during AQI lookup: {e}")