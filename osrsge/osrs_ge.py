import aiohttp
import discord
from redbot.core import commands
from redbot.core.bot import Red
from typing import Optional, List
import asyncio

class OSRSGE(commands.Cog):
    """Old School RuneScape Grand Exchange price lookup tool."""
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.version = "1.0.0"
        
        print(f"OSRS GE cog initialized - Version {self.version}")

    async def cog_load(self):
        """Called when the cog is loaded."""
        print(f"OSRS GE cog loaded - Version {self.version}")

    def cog_unload(self):
        """Called when the cog is unloaded."""
        asyncio.create_task(self.session.close())
        print(f"OSRS GE cog unloaded - Version {self.version}")

    def format_number(self, num: int) -> str:
        """Format large numbers with appropriate suffixes."""
        if num >= 1000000000:
            return f"{num/1000000000:.1f}B"
        elif num >= 1000000:
            return f"{num/1000000:.1f}M"
        elif num >= 1000:
            return f"{num/1000:.1f}K"
        else:
            return f"{num:,}"

    def parse_price_string(self, price_str) -> Optional[int]:
        """Parse a price string from the OSRS API into an integer."""
        if not price_str or price_str == 'N/A':
            return None
        
        try:
            # Remove commas and convert to string
            price_str = str(price_str).replace(',', '').strip()
            
            # Handle 'k' and 'm' suffixes
            if price_str.endswith('k'):
                return int(float(price_str[:-1]) * 1000)
            elif price_str.endswith('m'):
                return int(float(price_str[:-1]) * 1000000)
            else:
                return int(float(price_str))
        except (ValueError, TypeError):
            return None

    async def fetch_ge_prices(self, item_name: str) -> Optional[dict]:
        """Fetch Grand Exchange prices for an item using the OSRS API."""
        try:
            print(f"Searching for item: '{item_name}'")
            
            # Clean the search term
            search_term = item_name.lower().strip()
            first_letter = search_term[0] if search_term else 'a'
            
            # Search for the item
            target_item = None
            
            # Try first letter search
            search_url = f"https://secure.runescape.com/m=itemdb_oldschool/api/catalogue/items.json?category=1&alpha={first_letter}&page=1"
            
            async with self.session.get(search_url) as response:
                if response.status == 200:
                    try:
                        search_data = await response.json()
                        items = search_data.get('items', [])
                        
                        # Look for exact or partial matches
                        for item in items:
                            item_name_lower = item['name'].lower()
                            
                            # Exact match
                            if item_name_lower == search_term:
                                target_item = item
                                break
                            
                            # Partial match
                            if search_term in item_name_lower:
                                target_item = item
                                break
                    
                    except Exception as e:
                        print(f"Error parsing search results: {e}")
            
            if not target_item:
                print(f"No item found matching '{item_name}'")
                return None
            
            print(f"Found item: {target_item['name']} (ID: {target_item['id']})")
            
            # Get detailed price information
            detail_url = f"https://secure.runescape.com/m=itemdb_oldschool/api/catalogue/detail.json?item={target_item['id']}"
            
            async with self.session.get(detail_url) as response:
                if response.status == 200:
                    try:
                        detail_data = await response.json()
                        item_detail = detail_data.get('item', {})
                        
                        # Parse current price
                        current_price_str = item_detail.get('current', {}).get('price', '0')
                        current_price = self.parse_price_string(current_price_str)
                        
                        # Parse today's price for change calculation
                        today_price_str = item_detail.get('today', {}).get('price', '0')
                        today_price = self.parse_price_string(today_price_str)
                        
                        # Calculate price change
                        price_change = None
                        price_change_percent = None
                        
                        if current_price and today_price and today_price != 0:
                            price_change = current_price - today_price
                            price_change_percent = (price_change / today_price) * 100
                        
                        return {
                            'id': target_item['id'],
                            'name': item_detail.get('name', target_item['name']),
                            'description': item_detail.get('description', ''),
                            'current_price': current_price,
                            'today_price': today_price,
                            'price_change': price_change,
                            'price_change_percent': price_change_percent,
                            'icon': item_detail.get('icon', ''),
                            'icon_large': item_detail.get('icon_large', ''),
                            'type': item_detail.get('type', ''),
                            'members': item_detail.get('members', 'true') == 'true',
                            'day30_trend': item_detail.get('day30', {}).get('trend', 'neutral'),
                            'day90_trend': item_detail.get('day90', {}).get('trend', 'neutral'),
                            'day180_trend': item_detail.get('day180', {}).get('trend', 'neutral'),
                            'day30_change': item_detail.get('day30', {}).get('change', 'N/A'),
                            'day90_change': item_detail.get('day90', {}).get('change', 'N/A'),
                            'day180_change': item_detail.get('day180', {}).get('change', 'N/A')
                        }
                        
                    except Exception as e:
                        print(f"Error parsing item details: {e}")
                        return None
                else:
                    print(f"Failed to fetch item details, status: {response.status}")
                    return None
                    
        except Exception as e:
            print(f"Error in fetch_ge_prices: {e}")
            return None

    def get_price_emoji(self, trend: str, change_percent: float = None) -> str:
        """Get appropriate emoji for price trends."""
        if change_percent is not None:
            if change_percent > 5:
                return "📈🔥"
            elif change_percent > 0:
                return "📈"
            elif change_percent < -5:
                return "📉💥"
            elif change_percent < 0:
                return "📉"
            else:
                return "➡️"
        
        trend_emojis = {
            'positive': '📈',
            'negative': '📉',
            'neutral': '➡️'
        }
        return trend_emojis.get(trend.lower(), '➡️')

    def get_popular_items(self) -> List[str]:
        """Get a list of popular OSRS items for suggestions."""
        return [
            "Abyssal whip", "Dragon scimitar", "Dragon claws", "Bandos chestplate", 
            "Armadyl crossbow", "Twisted bow", "Scythe of vitur", "Tumeken's shadow", 
            "Dragon hunter lance", "Toxic blowpipe", "Trident of the seas", 
            "Occult necklace", "Berserker ring (i)", "Dragon boots", "Barrows gloves",
            "Fire cape", "Infernal cape", "Ava's assembler", "Shark", "Karambwan", 
            "Prayer potion(4)", "Super combat potion(4)", "Ranging potion(4)",
            "Magic logs", "Yew logs", "Dragon bones", "Big bones", "Rune ore", 
            "Adamant ore", "Nature rune", "Blood rune", "Death rune", "Chaos rune"
        ]

    def create_ge_embed(self, item_data: dict) -> discord.Embed:
        """Create a detailed Grand Exchange embed for an item."""
        name = item_data['name']
        current_price = item_data['current_price']
        price_change = item_data['price_change']
        price_change_percent = item_data['price_change_percent']
        
        # Determine embed color based on price trend
        if price_change_percent and price_change_percent > 0:
            color = 0x00FF00  # Green for positive
        elif price_change_percent and price_change_percent < 0:
            color = 0xFF0000  # Red for negative
        else:
            color = 0xFFD700  # Gold for neutral
        
        embed = discord.Embed(
            title=f"💰 Grand Exchange: {name}",
            color=color,
            url=f"https://oldschool.runescape.wiki/w/{name.replace(' ', '_')}"
        )
        
        # Add item icon if available
        if item_data.get('icon_large'):
            embed.set_thumbnail(url=item_data['icon_large'])
        
        # Current price and daily change
        price_emoji = self.get_price_emoji('', price_change_percent)
        price_text = f"**Current Price:** {self.format_number(current_price)} gp\n"
        
        if price_change is not None:
            change_sign = "+" if price_change >= 0 else ""
            price_text += f"**Daily Change:** {change_sign}{self.format_number(price_change)} gp"
            
            if price_change_percent is not None:
                price_text += f" ({change_sign}{price_change_percent:.1f}%)"
        
        price_text += f" {price_emoji}"
        
        embed.add_field(
            name="💵 Price Information",
            value=price_text,
            inline=True
        )
        
        # Item details
        details_text = f"**Type:** {item_data.get('type', 'Unknown')}\n"
        details_text += f"**Members:** {'Yes' if item_data.get('members') else 'No'}\n"
        details_text += f"**Item ID:** {item_data['id']}"
        
        embed.add_field(
            name="ℹ️ Item Details",
            value=details_text,
            inline=True
        )
        
        # Long-term trends
        trends_text = ""
        trend_periods = [
            ("30 Day", item_data['day30_trend'], item_data['day30_change']),
            ("90 Day", item_data['day90_trend'], item_data['day90_change']),
            ("180 Day", item_data['day180_trend'], item_data['day180_change'])
        ]
        
        for period, trend, change in trend_periods:
            trend_emoji = self.get_price_emoji(trend)
            trends_text += f"**{period}:** {change} {trend_emoji}\n"
        
        embed.add_field(
            name="📊 Long-term Trends",
            value=trends_text,
            inline=True
        )
        
        # Item description
        if item_data.get('description'):
            description = item_data['description']
            if len(description) > 200:
                description = description[:200] + "..."
            
            embed.add_field(
                name="📝 Description",
                value=description,
                inline=False
            )
        
        # Popular price calculations
        if current_price:
            calculations_text = ""
            quantities = [100, 1000, 10000]
            
            for qty in quantities:
                if qty <= 10000 or current_price <= 1000:  # Avoid huge numbers for expensive items
                    total_value = current_price * qty
                    calculations_text += f"**{qty:,}x:** {self.format_number(total_value)} gp\n"
            
            if calculations_text:
                embed.add_field(
                    name="🧮 Quick Calculations",
                    value=calculations_text,
                    inline=True
                )
        
        embed.set_footer(text=f"💡 Prices update daily • Data from OSRS Grand Exchange API • v{self.version}")
        
        return embed

    @commands.command(name="ge", aliases=["grandexchange", "price", "osrsge"])
    async def grand_exchange(self, ctx, *, item_name: str):
        """
        Fetch Grand Exchange prices and trends for any OSRS item.
        
        Provides detailed item information including current price, daily change,
        long-term trends, and market insights.
        
        Examples:
        .ge whip
        .grandexchange "dragon scimitar"
        .price "twisted bow"
        
        Features:
        • Real-time Grand Exchange prices
        • Daily price change and percentage
        • Long-term price trends (30, 90, 180 days)
        • Market insights and investment opportunities
        • Item descriptions and details
        • Quick price calculations for common quantities
        """
        async with ctx.typing():
            item_data = await self.fetch_ge_prices(item_name)
            
            if item_data:
                embed = self.create_ge_embed(item_data)
                await ctx.send(embed=embed)
            else:
                popular_items = self.get_popular_items()
                suggestions = "\n".join(f"• {item}" for item in popular_items[:5])
                
                embed = discord.Embed(
                    title="❌ Item Not Found",
                    description=f"Could not find item '{item_name}' on the Grand Exchange.\n\n"
                                f"**Suggestions:**\n{suggestions}\n\n"
                                f"**Make sure:**\n"
                                f"• The item name is spelled correctly\n"
                                f"• Use quotes for items with spaces: `.ge \"dragon scimitar\"`",
                    color=0xFF0000
                )
                embed.set_footer(text=f"v{self.version}")
                await ctx.send(embed=embed)

async def setup(bot: Red):
    await bot.add_cog(OSRSGE(bot))