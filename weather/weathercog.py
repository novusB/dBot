import discord
import aiohttp # For making asynchronous HTTP requests
import asyncio # For handling asynchronous operations
from redbot.core import commands, Config # Import commands framework and Config for settings
from redbot.core.utils.chat_formatting import humanize_list # For formatting lists nicely
from datetime import datetime, timedelta # For handling dates and times

class WeatherCog(commands.Cog):
    """
    A custom cog for Red Discord Bot to fetch current weather by ZIP code.
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
                await ctx.send(f"An unexpected error occurred while sending the API key to your DMs: {e}")
                self.bot.logger.error(f"WeatherCog viewapikey error: {e}")
        else:
            await ctx.send(
                f"No OpenWeatherMap API key is currently set. "
                f"Please set it using `{ctx.clean_prefix}set api openweathermap api_key <your_key>`."
            )

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user) # Cooldown to prevent API spam
    async def weather(self, ctx, zip_code: str, country_code: str = "us", days: int = None):
        """
        Gets the current weather conditions or a daily forecast for a given ZIP code.

        Usage:
        [p]weather <zip_code> [country_code] [days_for_forecast]

        Examples:
        [p]weather 90210                 - Current weather for Beverly Hills, USA
        [p]weather 78701 us             - Current weather for Austin, Texas, USA
        [p]weather SW1A0AA gb 3         - 3-day forecast for London, UK (max 5 days)
        [p]weather 90210 5              - 5-day forecast for Beverly Hills, USA
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

        if days is None: # Fetch current weather
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

        else: # Fetch forecast weather
            if not 1 <= days <= 5: # OpenWeatherMap free tier offers 5-day / 3-hour forecast
                return await ctx.send("Forecast is limited to a maximum of 5 days with the current API plan.")

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
                            title=f"Weather Forecast for {city_name} ({days} Days)",
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

                            # Only add the first entry for each day to represent the daily summary
                            # Or you could collect all entries for a day and calculate avg/min/max
                            if date_str not in daily_forecasts:
                                daily_forecasts[date_str] = {
                                    "temp_min": entry["main"]["temp_min"],
                                    "temp_max": entry["main"]["temp_max"],
                                    "description": entry["weather"][0]["description"].capitalize(),
                                    "icon": entry["weather"][0]["icon"],
                                    "date": dt_object.strftime("%a, %b %d") # E.g., Mon, Jun 09
                                }
                            # If it's the same day, update min/max temperatures
                            else:
                                daily_forecasts[date_str]["temp_min"] = min(daily_forecasts[date_str]["temp_min"], entry["main"]["temp_min"])
                                daily_forecasts[date_str]["temp_max"] = max(daily_forecasts[date_str]["temp_max"], entry["main"]["temp_max"])

                        # Add fields for each day up to the requested 'days'
                        current_day_count = 0
                        for date_key in sorted(daily_forecasts.keys()):
                            if current_day_count >= days:
                                break
                            
                            forecast = daily_forecasts[date_key]
                            embed.add_field(
                                name=forecast["date"],
                                value=(
                                    f"Temp: {forecast['temp_min']:.0f}{temp_unit} - {forecast['temp_max']:.0f}{temp_unit}\n"
                                    f"Condition: {forecast['description']}"
                                ),
                                inline=False
                            )
                            current_day_count += 1
                            
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