import aiohttp
import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, pagify
from typing import Optional, List, Dict, Any
import asyncio
import json
from datetime import datetime, timedelta
import logging

log = logging.getLogger("red.cogs.osrsge")

class OSRSGE(commands.Cog):
    """Old School RuneScape Grand Exchange price lookup tool."""
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=7829463052, force_registration=True)
        self.session = aiohttp.ClientSession()
        self.version = "1.3.0"
        self.debug_mode = False
        
        # Initialize default config
        default_global = {
            "version": self.version,
            "debug_mode": False
        }
        default_user = {
            "favorite_items": [],
            "search_history": []
        }
        self.config.register_global(**default_global)
        self.config.register_user(**default_user)

    async def cog_load(self):
        """Called when the cog is loaded."""
        await self.config.version.set(self.version)
        self.debug_mode = await self.config.debug_mode()

    def cog_unload(self):
        """Called when the cog is unloaded."""
        asyncio.create_task(self.session.close())

    def format_number(self, num: int) -> str:
        """Format large numbers with appropriate suffixes."""
        if num is None:
            return "N/A"
        if num >= 1000000000:
            return f"{num/1000000000:.1f}B"
        elif num >= 1000000:
            return f"{num/1000000:.1f}M"
        elif num >= 1000:
            return f"{num/1000:.1f}K"
        else:
            return f"{num:,}"

    def format_timestamp(self, timestamp: int) -> str:
        """Format Unix timestamp to readable time."""
        if not timestamp:
            return "Unknown"
        try:
            dt = datetime.fromtimestamp(timestamp)
            now = datetime.now()
            diff = now - dt
            
            if diff.days > 0:
                return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
            elif diff.seconds > 3600:
                hours = diff.seconds // 3600
                return f"{hours} hour{'s' if hours != 1 else ''} ago"
            elif diff.seconds > 60:
                minutes = diff.seconds // 60
                return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            else:
                return "Just now"
        except:
            return "Unknown"

    async def debug_log(self, message: str):
        """Log debug messages if debug mode is enabled."""
        if self.debug_mode:
            log.info(f"[DEBUG] {message}")

    async def get_item_mapping(self) -> Dict[str, Any]:
        """Get item mapping from OSRS Wiki API."""
        try:
            await self.debug_log("Fetching item mapping from API")
            mapping_url = "https://prices.runescape.wiki/api/v1/osrs/mapping"
            
            async with self.session.get(mapping_url) as response:
                if response.status == 200:
                    mapping_data = await response.json()
                    
                    # Convert to dict for faster lookups
                    item_mapping = {item['name'].lower(): item for item in mapping_data}
                    await self.debug_log(f"Loaded {len(item_mapping)} items in mapping")
                    
                    return item_mapping
                else:
                    await self.debug_log(f"Failed to fetch item mapping, status: {response.status}")
                    return {}
        except Exception as e:
            await self.debug_log(f"Error fetching item mapping: {e}")
            return {}

    async def get_latest_prices(self) -> Dict[str, Any]:
        """Get latest prices for all items."""
        try:
            await self.debug_log("Fetching latest prices from API")
            prices_url = "https://prices.runescape.wiki/api/v1/osrs/latest"
            
            async with self.session.get(prices_url) as response:
                if response.status == 200:
                    prices_data = await response.json()
                    latest_prices = prices_data.get('data', {})
                    await self.debug_log(f"Loaded latest prices for {len(latest_prices)} items")
                    return latest_prices
                else:
                    await self.debug_log(f"Failed to fetch latest prices, status: {response.status}")
                    return {}
        except Exception as e:
            await self.debug_log(f"Error fetching latest prices: {e}")
            return {}

    async def get_price_history(self, item_id: int, timeframe: str) -> List[Dict[str, Any]]:
        """Get price history for an item."""
        try:
            await self.debug_log(f"Fetching {timeframe} history for item {item_id}")
            history_url = f"https://prices.runescape.wiki/api/v1/osrs/{timeframe}?id={item_id}"
            
            async with self.session.get(history_url) as response:
                if response.status == 200:
                    history_data = await response.json()
                    data_points = history_data.get('data', [])
                    await self.debug_log(f"Loaded {len(data_points)} data points for {timeframe} history")
                    return data_points
                else:
                    await self.debug_log(f"Failed to fetch {timeframe} history, status: {response.status}")
                    return []
        except Exception as e:
            await self.debug_log(f"Error fetching {timeframe} history: {e}")
            return []

    async def fetch_comprehensive_ge_data(self, item_name: str) -> Optional[Dict[str, Any]]:
        """Fetch comprehensive Grand Exchange data."""
        try:
            await self.debug_log(f"Processing request for item: '{item_name}'")
            
            # Clean the search term
            search_term = item_name.lower().strip()
            
            # Get item mapping
            item_mapping = await self.get_item_mapping()
            if not item_mapping:
                await self.debug_log("No item mapping available")
                return None
            
            # Find the item in the mapping
            target_item = None
            best_match_score = 0

            # Try exact match first
            if search_term in item_mapping:
                target_item = item_mapping[search_term]
                await self.debug_log(f"Exact match found: {target_item['name']}")
            else:
                # Fuzzy matching - try multiple approaches
                await self.debug_log(f"Trying fuzzy matching for '{search_term}'")
                
                # Approach 1: Partial matches
                for item_name_lower, item_data in item_mapping.items():
                    # Check if search term is contained in item name
                    if search_term in item_name_lower:
                        score = len(search_term) / len(item_name_lower)
                        if score > best_match_score:
                            best_match_score = score
                            target_item = item_data
                            await self.debug_log(f"Partial match found: {item_data['name']} (score: {score:.2f})")
                
                # Approach 2: Check if item name starts with search term
                if not target_item:
                    for item_name_lower, item_data in item_mapping.items():
                        if item_name_lower.startswith(search_term):
                            score = len(search_term) / len(item_name_lower)
                            if score > best_match_score:
                                best_match_score = score
                                target_item = item_data
                                await self.debug_log(f"Prefix match found: {item_data['name']} (score: {score:.2f})")
                
                # Approach 3: Check if search term contains any words from item name
                if not target_item:
                    search_words = search_term.split()
                    for item_name_lower, item_data in item_mapping.items():
                        item_words = item_name_lower.split()
                        matching_words = sum(1 for word in search_words if any(word in item_word for item_word in item_words))
                        if matching_words > 0:
                            score = matching_words / len(search_words)
                            if score > best_match_score:
                                best_match_score = score
                                target_item = item_data
                                await self.debug_log(f"Word match found: {item_data['name']} (score: {score:.2f})")
            
            if not target_item:
                await self.debug_log(f"No item found matching '{item_name}'")
                return None
            
            item_id = target_item['id']
            item_name_found = target_item['name']
            await self.debug_log(f"Found item: {item_name_found} (ID: {item_id})")
            
            # Get latest prices
            latest_prices_data = await self.get_latest_prices()
            item_latest_prices = latest_prices_data.get(str(item_id))
            await self.debug_log(f"Latest prices for item {item_id}: {item_latest_prices}")
            
            if not item_latest_prices:
                await self.debug_log(f"No price data found for item ID {item_id}")
                # Debug: Show some available IDs
                available_ids = list(latest_prices_data.keys())[:10]
                await self.debug_log(f"Available price data IDs (first 10): {available_ids}")
                return None
            
            # Fetch history data for all timeframes
            timeframes = ['5m', '1h', '6h', '24h']
            history_data = {}
            
            for timeframe in timeframes:
                history_data[f'price_history_{timeframe}'] = await self.get_price_history(item_id, timeframe)
            
            # Compile comprehensive data
            comprehensive_data = {
                'mapping': target_item,
                'latest_prices': item_latest_prices,
                **history_data
            }
            
            # Process and analyze all the data
            processed_data = self.process_comprehensive_data(comprehensive_data)
            
            return processed_data
            
        except Exception as e:
            await self.debug_log(f"Error in fetch_comprehensive_ge_data: {e}")
            return None

    def process_comprehensive_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process and analyze all the fetched data."""
        mapping = raw_data['mapping']
        latest_prices = raw_data['latest_prices']
        
        if not latest_prices:
            return None
        
        # Extract basic price information
        high_price = latest_prices.get('high')
        low_price = latest_prices.get('low')
        high_time = latest_prices.get('highTime')
        low_time = latest_prices.get('lowTime')
        
        # Calculate current price
        current_price = None
        if high_price and low_price:
            current_price = (high_price + low_price) // 2
        elif high_price:
            current_price = high_price
        elif low_price:
            current_price = low_price
        
        if not current_price:
            return None
        
        # Analyze price trends from different timeframes
        price_trends = self.analyze_price_trends(raw_data)
        
        # Calculate volume statistics
        volume_stats = self.calculate_volume_stats(raw_data)
        
        # Determine market activity
        market_activity = self.determine_market_activity(raw_data)
        
        # Calculate trading metrics
        trading_metrics = self.calculate_trading_metrics(raw_data)
        
        # Compile comprehensive item data
        processed_data = {
            # Basic item information
            'id': mapping['id'],
            'name': mapping['name'],
            'examine': mapping.get('examine', 'No examine text available'),
            'members': mapping.get('members', True),
            'lowalch': mapping.get('lowalch'),
            'highalch': mapping.get('highalch'),
            'limit': mapping.get('limit'),
            'value': mapping.get('value'),
            'icon': mapping.get('icon'),
            
            # Current pricing
            'current_price': current_price,
            'high_price': high_price,
            'low_price': low_price,
            'high_time': high_time,
            'low_time': low_time,
            
            # Price trends
            'price_trends': price_trends,
            
            # Volume statistics
            'volume_stats': volume_stats,
            
            # Market activity
            'market_activity': market_activity,
            
            # Trading metrics
            'trading_metrics': trading_metrics
        }
        
        return processed_data

    def analyze_price_trends(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze price trends across different timeframes."""
        trends = {
            '5m': {'change': None, 'change_percent': None, 'trend': 'neutral'},
            '1h': {'change': None, 'change_percent': None, 'trend': 'neutral'},
            '6h': {'change': None, 'change_percent': None, 'trend': 'neutral'},
            '24h': {'change': None, 'change_percent': None, 'trend': 'neutral'}
        }
        
        # Analyze each timeframe
        for timeframe in ['5m', '1h', '6h', '24h']:
            history_key = f'price_history_{timeframe}'
            if raw_data.get(history_key):
                data_points = raw_data[history_key]
                if len(data_points) >= 2:
                    recent = data_points[-1]
                    old = data_points[0]
                    
                    recent_price = recent.get('avgHighPrice') or recent.get('avgLowPrice') or recent.get('highPriceVolume', 0)
                    old_price = old.get('avgHighPrice') or old.get('avgLowPrice') or old.get('highPriceVolume', 0)
                    
                    if recent_price and old_price and old_price > 0:
                        change = recent_price - old_price
                        change_percent = (change / old_price) * 100
                        
                        trends[timeframe]['change'] = change
                        trends[timeframe]['change_percent'] = change_percent
                        
                        if change_percent > 1:
                            trends[timeframe]['trend'] = 'positive'
                        elif change_percent < -1:
                            trends[timeframe]['trend'] = 'negative'
                        else:
                            trends[timeframe]['trend'] = 'neutral'
        
        return trends

    def calculate_volume_stats(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate volume statistics from price history."""
        volume_stats = {
            'total_volume_24h': 0,
            'avg_volume_per_hour': 0,
            'high_volume_trades': 0,
            'low_volume_trades': 0,
            'volume_trend': 'neutral'
        }
        
        # Calculate from 24h data if available
        if raw_data.get('price_history_24h'):
            data_points = raw_data['price_history_24h']
            total_high_volume = 0
            total_low_volume = 0
            
            for point in data_points:
                high_vol = point.get('highPriceVolume', 0)
                low_vol = point.get('lowPriceVolume', 0)
                
                total_high_volume += high_vol
                total_low_volume += low_vol
            
            volume_stats['total_volume_24h'] = total_high_volume + total_low_volume
            volume_stats['high_volume_trades'] = total_high_volume
            volume_stats['low_volume_trades'] = total_low_volume
            
            if len(data_points) > 0:
                volume_stats['avg_volume_per_hour'] = volume_stats['total_volume_24h'] // len(data_points)
        
        return volume_stats

    def determine_market_activity(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Determine market activity level."""
        latest_prices = raw_data.get('latest_prices', {})
        
        activity = {
            'level': 'unknown',
            'last_trade_time': None,
            'price_stability': 'unknown',
            'liquidity': 'unknown'
        }
        
        # Determine last trade time
        high_time = latest_prices.get('highTime')
        low_time = latest_prices.get('lowTime')
        
        if high_time and low_time:
            activity['last_trade_time'] = max(high_time, low_time)
        elif high_time:
            activity['last_trade_time'] = high_time
        elif low_time:
            activity['last_trade_time'] = low_time
        
        # Determine activity level based on recent trades
        if activity['last_trade_time']:
            time_since_trade = datetime.now().timestamp() - activity['last_trade_time']
            if time_since_trade < 300:  # 5 minutes
                activity['level'] = 'very_high'
            elif time_since_trade < 1800:  # 30 minutes
                activity['level'] = 'high'
            elif time_since_trade < 3600:  # 1 hour
                activity['level'] = 'medium'
            elif time_since_trade < 86400:  # 24 hours
                activity['level'] = 'low'
            else:
                activity['level'] = 'very_low'
        
        # Determine price stability
        high_price = latest_prices.get('high')
        low_price = latest_prices.get('low')
        
        if high_price and low_price and low_price > 0:
            spread_percent = ((high_price - low_price) / low_price) * 100
            if spread_percent < 1:
                activity['price_stability'] = 'very_stable'
            elif spread_percent < 3:
                activity['price_stability'] = 'stable'
            elif spread_percent < 10:
                activity['price_stability'] = 'moderate'
            else:
                activity['price_stability'] = 'volatile'
        
        return activity

    def calculate_trading_metrics(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate advanced trading metrics."""
        latest_prices = raw_data.get('latest_prices', {})
        mapping = raw_data.get('mapping', {})
        
        metrics = {
            'spread_gp': None,
            'spread_percent': None,
            'flip_profit': None,
            'roi_percent': None,
            'alch_profit': None,
            'margin_rating': 'unknown'
        }
        
        high_price = latest_prices.get('high')
        low_price = latest_prices.get('low')
        high_alch = mapping.get('highalch')
        
        if high_price and low_price:
            # Calculate spread
            spread = high_price - low_price
            spread_percent = (spread / low_price) * 100
            
            metrics['spread_gp'] = spread
            metrics['spread_percent'] = spread_percent
            metrics['flip_profit'] = spread
            metrics['roi_percent'] = spread_percent
            
            # Determine margin rating
            if spread_percent > 10:
                metrics['margin_rating'] = 'excellent'
            elif spread_percent > 5:
                metrics['margin_rating'] = 'good'
            elif spread_percent > 2:
                metrics['margin_rating'] = 'fair'
            else:
                metrics['margin_rating'] = 'poor'
        
        # Calculate alch profit
        if high_alch and high_price:
            # Assuming nature rune cost ~200gp
            alch_cost = 200
            metrics['alch_profit'] = high_alch - high_price - alch_cost
        
        return metrics

    def get_price_emoji(self, trend: str, change_percent: float = None) -> str:
        """Get appropriate emoji for price trends."""
        if change_percent is not None:
            if change_percent > 10:
                return "🚀"
            elif change_percent > 5:
                return "📈🔥"
            elif change_percent > 0:
                return "📈"
            elif change_percent < -10:
                return "💥"
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

    def get_activity_emoji(self, activity_level: str) -> str:
        """Get emoji for market activity level."""
        activity_emojis = {
            'very_high': '🔥',
            'high': '⚡',
            'medium': '🟡',
            'low': '🟠',
            'very_low': '🔴',
            'unknown': '❓'
        }
        return activity_emojis.get(activity_level, '❓')

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

    def create_comprehensive_embed(self, item_data: Dict[str, Any]) -> discord.Embed:
        """Create a comprehensive Grand Exchange embed with all available data."""
        name = item_data['name']
        current_price = item_data['current_price']
        high_price = item_data.get('high_price')
        low_price = item_data.get('low_price')
        price_trends = item_data.get('price_trends', {})
        market_activity = item_data.get('market_activity', {})
        trading_metrics = item_data.get('trading_metrics', {})
        volume_stats = item_data.get('volume_stats', {})
        
        # Determine embed color based on overall trend
        overall_trend = price_trends.get('24h', {}).get('change_percent', 0)
        if overall_trend > 0:
            color = 0x00FF00  # Green for positive
        elif overall_trend < 0:
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
        price_emoji = self.get_price_emoji('', overall_trend)
        price_text = f"**Current Price:** {self.format_number(current_price)} gp\n"
        
        if high_price and low_price:
            price_text += f"**Buy Price:** {self.format_number(high_price)} gp\n"
            price_text += f"**Sell Price:** {self.format_number(low_price)} gp\n"
        
        # Add last trade times
        if item_data.get('high_time'):
            price_text += f"**Last Buy:** {self.format_timestamp(item_data['high_time'])}\n"
        if item_data.get('low_time'):
            price_text += f"**Last Sell:** {self.format_timestamp(item_data['low_time'])}\n"
        
        price_text += f"{price_emoji}"
        
        embed.add_field(
            name="💵 Current Prices",
            value=price_text,
            inline=True
        )
        
        # Item details with all available information
        details_text = f"**Item ID:** {item_data['id']}\n"
        details_text += f"**Members:** {'Yes' if item_data.get('members') else 'No'}\n"
        
        if item_data.get('limit'):
            details_text += f"**Buy Limit:** {item_data['limit']:,}/4h\n"
        
        if item_data.get('highalch'):
            details_text += f"**High Alch:** {self.format_number(item_data['highalch'])} gp\n"
        
        if item_data.get('lowalch'):
            details_text += f"**Low Alch:** {self.format_number(item_data['lowalch'])} gp\n"
        
        if item_data.get('value'):
            details_text += f"**Store Value:** {self.format_number(item_data['value'])} gp"
        
        embed.add_field(
            name="ℹ️ Item Details",
            value=details_text,
            inline=True
        )
        
        # Market activity
        activity_level = market_activity.get('level', 'unknown')
        activity_emoji = self.get_activity_emoji(activity_level)
        
        activity_text = f"**Activity:** {activity_level.replace('_', ' ').title()} {activity_emoji}\n"
        
        if market_activity.get('price_stability'):
            stability = market_activity['price_stability'].replace('_', ' ').title()
            activity_text += f"**Stability:** {stability}\n"
        
        if market_activity.get('last_trade_time'):
            activity_text += f"**Last Trade:** {self.format_timestamp(market_activity['last_trade_time'])}"
        
        embed.add_field(
            name="📊 Market Activity",
            value=activity_text,
            inline=True
        )
        
        # Price trends across timeframes
        trends_text = ""
        for timeframe in ['5m', '1h', '6h', '24h']:
            trend_data = price_trends.get(timeframe, {})
            change_percent = trend_data.get('change_percent')
            
            if change_percent is not None:
                emoji = self.get_price_emoji(trend_data.get('trend', 'neutral'), change_percent)
                sign = "+" if change_percent >= 0 else ""
                trends_text += f"**{timeframe.upper()}:** {sign}{change_percent:.1f}% {emoji}\n"
        
        if trends_text:
            embed.add_field(
                name="📈 Price Trends",
                value=trends_text,
                inline=True
            )
        
        # Trading metrics
        if trading_metrics.get('spread_gp'):
            metrics_text = f"**Spread:** {self.format_number(trading_metrics['spread_gp'])} gp"
            
            if trading_metrics.get('spread_percent'):
                metrics_text += f" ({trading_metrics['spread_percent']:.1f}%)\n"
            else:
                metrics_text += "\n"
            
            if trading_metrics.get('flip_profit'):
                metrics_text += f"**Flip Profit:** {self.format_number(trading_metrics['flip_profit'])} gp\n"
            
            margin_rating = trading_metrics.get('margin_rating', 'unknown')
            metrics_text += f"**Margin:** {margin_rating.title()}\n"
            
            if trading_metrics.get('alch_profit'):
                alch_profit = trading_metrics['alch_profit']
                if alch_profit > 0:
                    metrics_text += f"**Alch Profit:** +{self.format_number(alch_profit)} gp"
                else:
                    metrics_text += f"**Alch Loss:** {self.format_number(alch_profit)} gp"
            
            embed.add_field(
                name="💰 Trading Metrics",
                value=metrics_text,
                inline=True
            )
        
        # Volume statistics
        if volume_stats.get('total_volume_24h', 0) > 0:
            volume_text = f"**24h Volume:** {self.format_number(volume_stats['total_volume_24h'])}\n"
            
            if volume_stats.get('high_volume_trades'):
                volume_text += f"**Buy Volume:** {self.format_number(volume_stats['high_volume_trades'])}\n"
            
            if volume_stats.get('low_volume_trades'):
                volume_text += f"**Sell Volume:** {self.format_number(volume_stats['low_volume_trades'])}"
            
            embed.add_field(
                name="📦 Volume Stats",
                value=volume_text,
                inline=True
            )
        
        # Item examine text
        if item_data.get('examine') and item_data['examine'] != 'No examine text available':
            embed.add_field(
                name="🔍 Examine",
                value=f"*{item_data['examine']}*",
                inline=False
            )
        
        # Quick calculations
        if current_price:
            calculations_text = ""
            quantities = [100, 1000, 10000]
            
            for qty in quantities:
                if qty <= 10000 or current_price <= 1000:
                    total_value = current_price * qty
                    calculations_text += f"**{qty:,}x:** {self.format_number(total_value)} gp\n"
            
            if calculations_text:
                embed.add_field(
                    name="🧮 Quick Calculations",
                    value=calculations_text,
                    inline=True
                )
        
        embed.set_footer(text=f"💡 Real-time data from OSRS Wiki • v{self.version}")
        
        return embed

    @commands.command(name="ge", aliases=["grandexchange", "price", "osrsge"])
    async def grand_exchange(self, ctx, *, item_name: str):
        """
        Fetch comprehensive Grand Exchange data for any OSRS item.
        
        Examples:
        .ge whip
        .grandexchange "dragon scimitar"
        .price "twisted bow"
        """
        # Handle quoted item names properly
        if item_name.startswith('"') and item_name.endswith('"'):
            item_name = item_name[1:-1]
        elif item_name.startswith("'") and item_name.endswith("'"):
            item_name = item_name[1:-1]
        
        async with ctx.typing():
            item_data = await self.fetch_comprehensive_ge_data(item_name)
            
            if item_data:
                embed = self.create_comprehensive_embed(item_data)
                await ctx.send(embed=embed)
                
                # Save to user's search history
                try:
                    async with self.config.user(ctx.author).search_history() as history:
                        history.append({
                            'item': item_data['name'],
                            'timestamp': datetime.now().isoformat(),
                            'price': item_data['current_price']
                        })
                        # Keep only last 10 searches
                        if len(history) > 10:
                            history.pop(0)
                except:
                    pass  # Don't fail if we can't save history
                    
            else:
                popular_items = self.get_popular_items()
                suggestions = "\n".join(f"• {item}" for item in popular_items[:5])
                
                embed = discord.Embed(
                    title="❌ Item Not Found",
                    description=f"Could not find item '{item_name}' on the Grand Exchange.\n\n"
                                f"**Suggestions:**\n{suggestions}\n\n"
                                f"**Make sure:**\n"
                                f"• The item name is spelled correctly\n"
                                f"• Use quotes for items with spaces: `.ge \"dragon scimitar\"`\n"
                                f"• The item is tradeable on the Grand Exchange",
                    color=0xFF0000
                )
                embed.set_footer(text=f"v{self.version}")
                await ctx.send(embed=embed)

    @commands.command(name="gedebug")
    @commands.is_owner()
    async def ge_debug(self, ctx, toggle: bool = None):
        """Toggle debug mode for GE commands."""
        if toggle is None:
            current = await self.config.debug_mode()
            await ctx.send(f"Debug mode is currently: {'**ON**' if current else '**OFF**'}")
            return
        
        await self.config.debug_mode.set(toggle)
        self.debug_mode = toggle
        status = "**ENABLED**" if toggle else "**DISABLED**"
        await ctx.send(f"GE Debug mode {status}")

    @commands.command(name="getest")
    @commands.is_owner()
    async def ge_test(self, ctx, *, item_name: str = "abyssal whip"):
        """Test GE API calls with detailed output."""
        # Handle quoted item names properly
        if item_name.startswith('"') and item_name.endswith('"'):
            item_name = item_name[1:-1]
        elif item_name.startswith("'") and item_name.endswith("'"):
            item_name = item_name[1:-1]
        
        await ctx.send(f"Testing GE API with item: {item_name}")
        
        # Enable debug mode temporarily
        old_debug = self.debug_mode
        self.debug_mode = True
        
        try:
            # Test item mapping
            await ctx.send("📡 Testing item mapping API...")
            mapping = await self.get_item_mapping()
            await ctx.send(f"✅ Mapping loaded: {len(mapping)} items")
            
            # Test search with better matching
            search_term = item_name.lower().strip()
            await ctx.send(f"🔍 Searching for: '{search_term}'")
            
            # Try exact match first
            target_item = None
            if search_term in mapping:
                target_item = mapping[search_term]
                await ctx.send(f"✅ Exact match found: {target_item['name']} (ID: {target_item['id']})")
            else:
                # Try fuzzy matching
                matches = []
                for item_name_lower, item_data in mapping.items():
                    if search_term in item_name_lower:
                        matches.append((item_data['name'], item_data['id']))
                        if len(matches) >= 5:  # Limit to first 5 matches
                            break
            
            if matches:
                await ctx.send(f"🔍 Found {len(matches)} partial matches:")
                for name, item_id in matches[:3]:
                    await ctx.send(f"  • {name} (ID: {item_id})")
                
                # Use the first match for testing
                target_item = mapping[matches[0][0].lower()]
                await ctx.send(f"✅ Using first match: {target_item['name']} (ID: {target_item['id']})")
            else:
                await ctx.send(f"❌ No matches found for '{search_term}'")
                # Show some sample items
                sample_items = list(mapping.keys())[:10]
                await ctx.send(f"Sample items in mapping: {sample_items}")
                return
        
        # Test prices
        await ctx.send("📡 Testing latest prices API...")
        prices = await self.get_latest_prices()
        await ctx.send(f"✅ Prices loaded: {len(prices)} items")
        
        item_price = prices.get(str(target_item['id']))
        if item_price:
            await ctx.send(f"✅ Price data found: {item_price}")
            
            # Test full data fetch
            await ctx.send("📡 Testing full data fetch...")
            full_data = await self.fetch_comprehensive_ge_data(item_name)
            if full_data:
                await ctx.send(f"✅ Full data processed successfully!")
                await ctx.send(f"Current price: {self.format_number(full_data['current_price'])} gp")
            else:
                await ctx.send("❌ Failed to process full data")
        else:
            await ctx.send(f"❌ No price data for ID {target_item['id']}")
            # Show some available IDs
            available = list(prices.keys())[:10]
            await ctx.send(f"Available price IDs: {available}")
            
    except Exception as e:
        await ctx.send(f"❌ Error during test: {e}")
        import traceback
        await ctx.send(f"Traceback: {traceback.format_exc()}")
    finally:
        # Restore debug mode
        self.debug_mode = old_debug

    @commands.command(name="gehistory", aliases=["gehist"])
    async def ge_history(self, ctx):
        """View your recent Grand Exchange search history."""
        try:
            history = await self.config.user(ctx.author).search_history()
            
            if not history:
                embed = discord.Embed(
                    title="📜 GE Search History",
                    description="You haven't searched for any items yet!",
                    color=0x8B4513
                )
                await ctx.send(embed=embed)
                return
            
            embed = discord.Embed(
                title="📜 Your Recent GE Searches",
                color=0x8B4513
            )
            
            history_text = ""
            for i, search in enumerate(reversed(history[-10:]), 1):
                timestamp = datetime.fromisoformat(search['timestamp'])
                time_ago = self.format_timestamp(timestamp.timestamp())
                price = self.format_number(search['price'])
                
                history_text += f"**{i}.** {search['item']} - {price} gp ({time_ago})\n"
            
            embed.add_field(
                name="Recent Searches",
                value=history_text,
                inline=False
            )
            
            embed.set_footer(text=f"Use .ge <item> to search for prices • v{self.version}")
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send("❌ Error retrieving search history.")

async def setup(bot: Red):
    await bot.add_cog(OSRSGE(bot))