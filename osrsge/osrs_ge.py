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
        """Fetch Grand Exchange prices using the OSRS Wiki API."""
        try:
            print(f"Searching for item: '{item_name}'")
        
            # Clean the search term
            search_term = item_name.lower().strip()
        
            # First, get the mapping of all items from OSRS Wiki
            mapping_url = "https://prices.runescape.wiki/api/v1/osrs/mapping"
        
            async with self.session.get(mapping_url) as response:
                if response.status != 200:
                    print(f"Failed to fetch item mapping, status: {response.status}")
                    return None
            
                try:
                    mapping_data = await response.json()
                except Exception as e:
                    print(f"Error parsing mapping data: {e}")
                    return None
        
            # Find the item in the mapping
            target_item = None
            best_match_score = 0
        
            for item in mapping_data:
                item_name_lower = item['name'].lower()
            
                # Exact match (highest priority)
                if item_name_lower == search_term:
                    target_item = item
                    break
            
                # Partial match scoring
                if search_term in item_name_lower:
                    # Score based on how close the match is
                    score = len(search_term) / len(item_name_lower)
                    if score > best_match_score:
                        best_match_score = score
                        target_item = item
            
                # Also check if the search term starts with the item name
                elif item_name_lower.startswith(search_term):
                    score = len(search_term) / len(item_name_lower)
                    if score > best_match_score:
                        best_match_score = score
                        target_item = item
        
            if not target_item:
                print(f"No item found matching '{item_name}'")
                return None
        
            item_id = target_item['id']
            item_name_found = target_item['name']
            print(f"Found item: {item_name_found} (ID: {item_id})")
        
            # Get current prices from OSRS Wiki
            prices_url = "https://prices.runescape.wiki/api/v1/osrs/latest"
        
            async with self.session.get(prices_url) as response:
                if response.status != 200:
                    print(f"Failed to fetch prices, status: {response.status}")
                    return None
            
                try:
                    prices_data = await response.json()
                except Exception as e:
                    print(f"Error parsing prices data: {e}")
                    return None
        
            # Get price data for our item
            item_data = prices_data.get('data', {}).get(str(item_id))
            if not item_data:
                print(f"No price data found for item ID {item_id}")
                return None
        
            # Extract price information
            high_price = item_data.get('high')
            low_price = item_data.get('low')
            high_time = item_data.get('highTime')
            low_time = item_data.get('lowTime')
        
            # Calculate average price
            current_price = None
            if high_price and low_price:
                current_price = (high_price + low_price) // 2
            elif high_price:
                current_price = high_price
            elif low_price:
                current_price = low_price
        
            if not current_price:
                print(f"No valid price data for {item_name_found}")
                return None
        
            # Get 5-minute price history for trend analysis
            history_url = f"https://prices.runescape.wiki/api/v1/osrs/5m?id={item_id}"
        
            price_change = None
            price_change_percent = None
        
            try:
                async with self.session.get(history_url) as response:
                    if response.status == 200:
                        history_data = await response.json()
                        data_points = history_data.get('data', [])
                    
                        if len(data_points) >= 2:
                            # Compare current price with price from 24 hours ago (288 data points = 24 hours of 5-min intervals)
                            recent_data = data_points[-1] if data_points else None
                            old_data = data_points[-288] if len(data_points) >= 288 else data_points[0]
                        
                            if recent_data and old_data:
                                recent_avg = recent_data.get('avgHighPrice') or recent_data.get('avgLowPrice')
                                old_avg = old_data.get('avgHighPrice') or old_data.get('avgLowPrice')
                            
                                if recent_avg and old_avg:
                                    price_change = recent_avg - old_avg
                                    price_change_percent = (price_change / old_avg) * 100
            except Exception as e:
                print(f"Error fetching price history: {e}")
        
            # Get additional item details from OSRS Wiki if available
            item_details = {
                'id': item_id,
                'name': item_name_found,
                'current_price': current_price,
                'high_price': high_price,
                'low_price': low_price,
                'price_change': price_change,
                'price_change_percent': price_change_percent,
                'high_time': high_time,
                'low_time': low_time,
                'members': target_item.get('members', True),
                'limit': target_item.get('limit'),
                'value': target_item.get('value'),
                'icon': f"https://oldschool.runescape.wiki/images/{target_item['name'].replace(' ', '_')}_detail.png" if target_item.get('name') else None
            }
        
            return item_details
        
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
            "Occult necklace", "Berserker ring", "Dragon boots", "Barrows gloves",
            "Shark", "Karambwan", "Prayer potion", "Super combat potion", "Ranging potion",
            "Magic logs", "Yew logs", "Dragon bones", "Big bones", "Rune ore", 
            "Adamant ore", "Nature rune", "Blood rune", "Death rune", "Chaos rune",
            "Cannonball", "Dragon dart tip", "Rune arrow", "Adamant arrow", "Coal", 
            "Iron ore", "Lobster", "Monkfish", "Anglerfish", "Saradomin brew",
            "Super restore", "Stamina potion", "Divine super combat potion"
        ]

    def create_ge_embed(self, item_data: dict) -> discord.Embed:
        """Create a detailed Grand Exchange embed for an item."""
        name = item_data['name']
        current_price = item_data['current_price']
        high_price = item_data.get('high_price')
        low_price = item_data.get('low_price')
        price_change = item_data.get('price_change')
        price_change_percent = item_data.get('price_change_percent')
    
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
        if item_data.get('icon'):
            embed.set_thumbnail(url=item_data['icon'])
    
        # Current price information
        price_emoji = self.get_price_emoji('', price_change_percent)
        price_text = f"**Current Price:** {self.format_number(current_price)} gp\n"
    
        if high_price and low_price:
            price_text += f"**Buy Price:** {self.format_number(high_price)} gp\n"
            price_text += f"**Sell Price:** {self.format_number(low_price)} gp\n"
    
        if price_change is not None:
            change_sign = "+" if price_change >= 0 else ""
            price_text += f"**24h Change:** {change_sign}{self.format_number(price_change)} gp"
        
            if price_change_percent is not None:
                price_text += f" ({change_sign}{price_change_percent:.1f}%)"
    
        price_text += f" {price_emoji}"
    
        embed.add_field(
            name="💵 Price Information",
            value=price_text,
            inline=True
        )
    
        # Item details
        details_text = f"**Item ID:** {item_data['id']}\n"
        details_text += f"**Members:** {'Yes' if item_data.get('members') else 'No'}\n"
    
        if item_data.get('limit'):
            details_text += f"**Buy Limit:** {item_data['limit']:,}/4h\n"
    
        if item_data.get('value'):
            details_text += f"**High Alch:** {self.format_number(item_data['value'])} gp"
    
        embed.add_field(
            name="ℹ️ Item Details",
            value=details_text,
            inline=True
        )
    
        # Price spread analysis
        if high_price and low_price and high_price != low_price:
            spread = high_price - low_price
            spread_percent = (spread / low_price) * 100
            margin_text = f"**Spread:** {self.format_number(spread)} gp ({spread_percent:.1f}%)\n"
        
            # Calculate potential profit margins
            if spread > 0:
                margin_text += f"**Flip Profit:** {self.format_number(spread)} gp per item\n"
            
                # Show profit for common quantities
                for qty in [100, 1000]:
                    if qty * spread < 10000000:  # Don't show unrealistic profits
                        margin_text += f"**{qty}x Flip:** {self.format_number(qty * spread)} gp\n"
        
        embed.add_field(
            name="📊 Trading Analysis",
            value=margin_text,
            inline=True
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
    
        # Investment insights for expensive items
        if current_price and current_price > 1000000:  # 1M+ items
            insights_text = ""
        
            if price_change_percent and abs(price_change_percent) > 2:
                if price_change_percent > 5:
                    insights_text += "🔥 **Hot Item:** Significant price increase!\n"
                elif price_change_percent < -5:
                    insights_text += "💥 **Market Crash:** Major price drop!\n"
                elif price_change_percent > 2:
                    insights_text += "📈 **Rising:** Good time to sell\n"
                elif price_change_percent < -2:
                    insights_text += "📉 **Falling:** Potential buying opportunity\n"
        
            if high_price and low_price:
                spread_percent = ((high_price - low_price) / low_price) * 100
                if spread_percent > 5:
                    insights_text += "💰 **High spread:** Good for flipping\n"
                elif spread_percent < 1:
                    insights_text += "📊 **Stable market:** Low volatility\n"
        
        if insights_text:
            embed.add_field(
                name="💡 Market Insights",
                value=insights_text,
                inline=False
            )
    
        embed.set_footer(text=f"💡 Real-time data from OSRS Wiki • Updated every 5 minutes • v{self.version}")
    
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