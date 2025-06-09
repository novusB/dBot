import discord
import aiohttp # For making asynchronous HTTP requests
import asyncio # For handling asynchronous operations
from redbot.core import commands, Config # Import commands framework and Config for settings
from redbot.core.utils.chat_formatting import humanize_list # For formatting lists nicely

class WeatherCog(commands.Cog):
    """
    A custom cog for Red Discord Bot to fetch current weather by ZIP code.
    """

    # Default configuration for the cog.
    # We use a global scope for settings that apply across all guilds,
    # and a guild scope if we wanted guild-specific API keys (not used here).
    # In this case, the API key is stored globally for the bot owner.
    _config_schema = {
        "api_key": "" # Key to store the OpenWeatherMap API key
    }

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
        # Register the default configuration schema.
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
        Sets the OpenWeatherMap API key for the weather cog.
        You can get an API key from: https://openweathermap.org/api
        Note: It might take a few minutes (or occasionally longer) for a new API key to become active on OpenWeatherMap's side.

        Usage: [p]weatherset setapikey <your_api_key_here>
        """
        await self.config.api_key.set(api_key) # Store the API key in Red's config
        await ctx.send("OpenWeatherMap API key has been set!")

    @weatherset.command()
    async def viewapikey(self, ctx):
        """
        Views the currently stored OpenWeatherMap API key.
        This command is only usable by the bot owner.
        """
        api_key = await self.config.api_key()
        if api_key:
            await ctx.author.send(f"The current OpenWeatherMap API key is: `{api_key}`")
            if ctx.guild: # Send a public confirmation if used in a guild
                await ctx.send("The API key has been sent to your DMs.")
        else:
            await ctx.send("No OpenWeatherMap API key is currently set.")

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user) # Cooldown to prevent API spam
    async def weather(self, ctx, zip_code: str, country_code: str = "us"):
        """
        Gets the current weather conditions for a given ZIP code.

        Usage:
        [p]weather <zip_code> [country_code]

        Examples:
        [p]weather 90210
        [p]weather 78701 us
        [p]weather SW1A0AA gb (for UK postcodes)
        """
        api_key = await self.config.api_key() # Retrieve the API key from config

        if not api_key:
            return await ctx.send(
                f"The OpenWeatherMap API key is not set. Please set it using `{ctx.clean_prefix}weatherset setapikey <your_api_key>`."
            )

        # Basic validation for ZIP code (can be expanded for specific country formats)
        if not zip_code.isalnum(): # Check if it's alphanumeric (basic for US, UK has letters)
            return await ctx.send("Please provide a valid ZIP/postal code.")

        # OpenWeatherMap API endpoint for current weather by ZIP code
        # Using 'imperial' for Fahrenheit, 'metric' for Celsius, 'standard' for Kelvin
        units = "imperial" # Default to Fahrenheit for US, can be made configurable
        base_url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "zip": f"{zip_code},{country_code}",
            "appid": api_key,
            "units": units
        }

        try:
            # Make the asynchronous HTTP GET request to the OpenWeatherMap API
            async with self.session.get(base_url, params=params) as response:
                if response.status == 200: # HTTP 200 OK
                    data = await response.json() # Parse the JSON response

                    # Extract relevant weather information
                    city_name = data["name"]
                    weather_description = data["weather"][0]["description"].capitalize()
                    temperature = data["main"]["temp"]
                    feels_like = data["main"]["feels_like"]
                    humidity = data["main"]["humidity"]
                    wind_speed = data["wind"]["speed"]
                    
                    # Determine unit symbol based on 'units' parameter
                    temp_unit = "°F" if units == "imperial" else "°C"
                    speed_unit = "mph" if units == "imperial" else "m/s"

                    # Create a Discord Embed to display the weather
                    embed = discord.Embed(
                        title=f"Current Weather in {city_name}",
                        description=f"**{weather_description}**",
                        color=discord.Color.blue() # You can choose a different color
                    )
                    embed.add_field(name="Temperature", value=f"{temperature}{temp_unit} (Feels like {feels_like}{temp_unit})", inline=False)
                    embed.add_field(name="Humidity", value=f"{humidity}%", inline=True)
                    embed.add_field(name="Wind Speed", value=f"{wind_speed} {speed_unit}", inline=True)
                    embed.set_footer(text="Powered by OpenWeatherMap")
                    embed.set_thumbnail(url=f"http://openweathermap.org/img/wn/{data['weather'][0]['icon']}@2x.png")

                    await ctx.send(embed=embed)

                elif response.status == 401: # Unauthorized - likely invalid API key
                    await ctx.send(f"Error: Invalid OpenWeatherMap API key. Please check your key with `{ctx.clean_prefix}weatherset setapikey`.")
                elif response.status == 404: # Not Found - likely invalid ZIP code
                    await ctx.send("Error: ZIP/postal code or country not found. Please check your input.")
                else: # Other HTTP errors
                    await ctx.send(f"An unexpected error occurred with the weather API (Status: {response.status}).")

        except aiohttp.ClientConnectorError:
            await ctx.send("Could not connect to the weather API. Please try again later.")
        except asyncio.TimeoutError:
            await ctx.send("The weather API request timed out. Please try again later.")
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
            self.bot.logger.error(f"WeatherCog error: {e}") # Log the error for debugging