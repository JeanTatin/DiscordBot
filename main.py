import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
import datetime
import asyncio
import requests
import pytz
from keep_alive import keep_alive

keep_alive()
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="§", intents=intents)

AUTHORIZED_USER_ID = [401680916063322112, 760543763340460033]
VIP_CHANNEL_ID = 1396953333918339143
MAIN_CHANNEL_ID = 1396937201992073280
VIP_ROLE_ID = 1396955379874795690
PUMP_ROLE_ID = 1396952062952079531

###### PUMP

# Fuseau horaire Paris
tz_paris = pytz.timezone("Europe/Paris")

async def ask_question(user, question, check):
    try:
        await user.send(question)
        response = await bot.wait_for('message', check=check, timeout=120.0)
        return response.content.strip()
    except asyncio.TimeoutError:
        await user.send("⏰ Temps écoulé. Merci de recommencer la configuration.")
        return None

def get_current_time_paris_api():
    url = "http://worldtimeapi.org/api/timezone/Europe/Paris"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        dt = datetime.datetime.fromisoformat(data["datetime"].replace("Z", "+00:00"))
        return dt.astimezone(tz_paris)
    except Exception as e:
        print(f"[Erreur API heure Paris] {e}")
        return None

def get_current_time_paris_local(last_sync_time=None, last_sync_dt=None):
    if last_sync_time is None or last_sync_dt is None:
        return datetime.datetime.now(tz_paris)
    now = datetime.datetime.now(datetime.timezone.utc)
    elapsed = now - last_sync_time
    return last_sync_dt + elapsed

@bot.command()
async def start_pump(ctx):
    await ctx.message.delete()

    if ctx.author.id not in AUTHORIZED_USER_ID:
        try:
            await ctx.author.send("⛔ Tu n'as pas la permission d'utiliser cette commande.")
        except discord.Forbidden:
            pass
        return


    user = ctx.author

    def check(m):
        return m.author == user and isinstance(m.channel, discord.DMChannel)

    try:
        await user.send("⚙️ Merci de remplir les informations pour configurer le pump :")

        coin = await ask_question(user, "💰 Quel est le **nom du coin** ?", check)
        if coin is None:
            return

        address = await ask_question(user, "📩 Quelle est l'**adresse du token** ?", check)
        if address is None:
            return

        exchange = await ask_question(user, "🏦 Quelle est l'**adresse de l'exchange** ?", check)
        if exchange is None:
            return

        start_str = await ask_question(user, "🕒 Quelle est l'**heure de début** du pump ? (format HH:MM, 24h)", check)
        if start_str is None:
            return

        end_str = await ask_question(user, "🕒 Quelle est l'**heure de fin** du pump ? (format HH:MM, 24h)", check)
        if end_str is None:
            return

        # Préparation PUMP 1 (temps avant début)
        prep1_str = await ask_question(user, "⏳ Combien de temps avant le pump envoyer la préparation PUMP 1 ? (format HH:MM:SS)", check)
        if prep1_str is None:
            return

        # Préparation PUMP 2 (temps avant début)
        prep2_str = await ask_question(user, "⏳ Combien de temps avant le pump envoyer la préparation PUMP 2 ? (format HH:MM:SS)", check)
        if prep2_str is None:
            return

        vip_input = await ask_question(user, "💎 Activer le mode VIP ? (oui/non)", check)
        if vip_input is None:
            return

        vip = vip_input.lower() == "oui"
        vip_advance = None
        if vip:
            vip_advance_str = await ask_question(user, "⏳ Combien de temps avant le pump envoyer le message VIP ? (format HH:MM:SS)", check)
            if vip_advance_str is None:
                return
            try:
                h, m, s = map(int, vip_advance_str.split(":"))
                vip_advance = datetime.timedelta(hours=h, minutes=m, seconds=s)
            except Exception:
                await user.send("❌ Format invalide pour le temps. Utilise HH:MM:SS.")
                return

        try:
            now_paris = datetime.datetime.now(tz_paris)
            start = datetime.datetime.strptime(start_str, "%H:%M")
            end = datetime.datetime.strptime(end_str, "%H:%M")

            start = tz_paris.localize(datetime.datetime(now_paris.year, now_paris.month, now_paris.day, start.hour, start.minute))
            end = tz_paris.localize(datetime.datetime(now_paris.year, now_paris.month, now_paris.day, end.hour, end.minute))

            if start < now_paris:
                start += datetime.timedelta(days=1)
            if end < now_paris:
                end += datetime.timedelta(days=1)

            # Parse temps avant pour préparations
            try:
                h1, m1, s1 = map(int, prep1_str.split(":"))
                prep1_advance = datetime.timedelta(hours=h1, minutes=m1, seconds=s1)
            except Exception:
                await user.send("❌ Format invalide pour la préparation PUMP 1. Utilise HH:MM:SS.")
                return

            try:
                h2, m2, s2 = map(int, prep2_str.split(":"))
                prep2_advance = datetime.timedelta(hours=h2, minutes=m2, seconds=s2)
            except Exception:
                await user.send("❌ Format invalide pour la préparation PUMP 2. Utilise HH:MM:SS.")
                return

        except ValueError:
            await user.send("❌ Format d'heure invalide. Utilise HH:MM (24h).")
            return

        await user.send(
            f"✅ Configuration enregistrée !\n"
            f"**Coin :** {coin}\n"
            f"**Adresse :** {address}\n"
            f"**Exchange :** {exchange}\n"
            f"**Début :** {start.strftime('%H:%M')}\n"
            f"**Fin :** {end.strftime('%H:%M')}\n"
            f"**Préparation PUMP 1 :** {prep1_str} avant\n"
            f"**Préparation PUMP 2 :** {prep2_str} avant\n"
            f"**VIP :** {'Oui' if vip else 'Non'}"
        )

        asyncio.create_task(schedule_pump(coin, address, exchange, start, end, vip, vip_advance, prep1_advance, prep2_advance))

    except discord.Forbidden:
        await ctx.send("❌ Impossible de t'envoyer un message privé. Active-les !", delete_after=10)

async def schedule_pump(coin, address, exchange, start, end, vip, vip_advance, prep1_advance, prep2_advance):
    await bot.wait_until_ready()

    main_channel = bot.get_channel(MAIN_CHANNEL_ID)
    vip_channel = bot.get_channel(VIP_CHANNEL_ID)

    vip_sent = False
    start_sent = False
    end_sent = False
    prep1_sent = False
    prep2_sent = False

    print(f"[Pump Scheduler] Programmé : coin={coin}, start={start}, end={end}, VIP={vip}")

    last_api_sync = None
    last_api_datetime = None

    while True:
        now_utc = datetime.datetime.now(datetime.timezone.utc)

        if last_api_sync is None or (now_utc - last_api_sync).total_seconds() > 300:
            api_time = get_current_time_paris_api()
            if api_time is not None:
                last_api_sync = now_utc
                last_api_datetime = api_time
                print(f"[Pump Scheduler] Heure Paris synchronisée via API : {api_time}")
            else:
                print("[Pump Scheduler] Erreur de synchro API, utilisation heure locale approximative.")
                last_api_sync = now_utc
                last_api_datetime = datetime.datetime.now(tz_paris)

        now = get_current_time_paris_local(last_api_sync, last_api_datetime)

        # Préparation PUMP 1
        if not prep1_sent:
            prep1_time = start - prep1_advance
            if now >= prep1_time:
                if main_channel:
                    embed_prep1 = discord.Embed(
                        title="⏳⚡ PUMP PREPARATION - STAGE 1 ⚡⏳",
                        description="⚠️ A massive pump is on the way ! \n ✅ Double-check your setup \n 💼 Top up your wallet \n\n ⚔️ Stay alert and sharp \n 🚀 Timing is everything. Don’t miss the launch",
                        color=0x95a5a6  # Gris
                    )
                    embed_prep1.set_footer(text="PUMP Signals powered by THE INSIDERS")
                    # Mention cachée dans content, mais pas dans embed
                    await main_channel.send(content=f"<@&{PUMP_ROLE_ID}> GET READY !", embed=embed_prep1, allowed_mentions=discord.AllowedMentions.none())
                prep1_sent = True

        # Préparation PUMP 2
        if not prep2_sent:
            prep2_time = start - prep2_advance
            if now >= prep2_time:
                if main_channel:
                    embed_prep2 = discord.Embed(
                        title="⏳⚡ PUMP PREPARATION - STAGE 2 ⚡⏳",
                        description="⚠️ A massive pump is on the way !\n ⏰ The next ping will be the PUMP signal ! \n\n ✅ Double-check your setup \n 💼 Top up your wallet \n\n ⚔️ Stay alert and sharp \n 🚀 Timing is everything. Don’t miss the launch",
                        color=0x95a5a6  # Gris
                    )
                    embed_prep2.set_footer(text="PUMP Signals powered by THE INSIDERS")
                    await main_channel.send(content=f"<@&{PUMP_ROLE_ID}> GET READY !", embed=embed_prep2, allowed_mentions=discord.AllowedMentions.none())
                prep2_sent = True

        # VIP message
        if vip and not vip_sent:
            vip_time = start - (vip_advance if vip_advance else datetime.timedelta(seconds=10))
            if now >= vip_time:
                if vip_channel:
                    embed_vip = discord.Embed(
                        title="💎🚨 VIP PUMP ALERT 🚨💎",
                        description=(
                            f"**🪙 Coin :** `${coin}`\n"
                            f"**🔗 Token Address :** {address}\n"
                            f"**🏦 Exchange :** {exchange}\n\n"
                            "⚠️ Important Reminder: Stay calm, trust the process, and don’t panic sell.Selling in 3 or 4 parts helps avoid major price drops and maximizes your gains. \n\n Be smart. Be early. Be VIP. 💼 🚀"
                        ),
                        color=0x8e44ad  # Violet VIP
                    )
                    embed_vip.set_footer(text="PUMP Signals powered by THE INSIDERS")
                    await vip_channel.send(content=f"<@&{VIP_ROLE_ID}> It's pump time !", embed=embed_vip)
                vip_sent = True

        # Début du pump
        if not start_sent and now >= start:
            if main_channel:
                embed_start = discord.Embed(
                    title="🚀🔥 THE PUMP IS LIVE NOW ! 🔥🚀",
                    description=(
                        f"**💰 Selected Coin :** `${coin}`\n"
                        f"**🏷️ Token Address :** `{address}`\n"
                        f"**🏦 Exchange :** {exchange}\n\n"
                        "📈 Strategy Reminder:To maximize your profits, avoid selling during the first dip. This helps prevent panic selling and keeps the price rising. \n\n 💎 Stay calm, follow the plan, and sell gradually (in 3 or 4 parts). \n\n Let's pump smart ! 💪 📊"
                    ),
                    color=0x2ecc71  # Vert
                )
                embed_start.set_author(name="", icon_url="")
                embed_start.set_footer(text="PUMP Signals powered by THE INSIDERS")
                await main_channel.send(content=f"<@&{PUMP_ROLE_ID}> It's pump time !", embed=embed_start)
            start_sent = True

        # Fin du pump
        if not end_sent and now >= end:
            if main_channel:
                embed_end = discord.Embed(
                    title="🛑 END OF THE PUMP 🛑",
                    description=(
                        f"💸 Coin : `${coin}`\n"
                        "📉 The pump has officially ended ...\n 😌 Stay calm & avoid panic selling. \n\n 💎 Stay calm, follow the plan, and sell gradually (in 3 or 4 parts).\n\n 📊 Stick to the plan, and secure your profits smartly.\n🔒 Consistency beats emotion every time."
                    ),
                    color=0xe74c3c  # Rouge
                )
                embed_end.set_author(name="", icon_url="")
                embed_end.set_footer(text="PUMP Signals powered by THE INSIDERS")
                await main_channel.send(content=f"<@&{PUMP_ROLE_ID}> The pump is finished !", embed=embed_end)
            end_sent = True
            break

        if (not vip or vip_sent) and start_sent and end_sent and prep1_sent and prep2_sent:
            break

        await asyncio.sleep(0.5)

##### PAIEMENT

CRYPTO_DATA = {
    "bitcoin": {
        "label": "Bitcoin",
        "description": "",
        "address": "bc1q4cpjy5ccxv3kzrjhdvzu6udzlsnd3tdkwcf9sw",
        "qr_url": "https://imgur.com/85A8AdZ"
    },
    "ethereum": {
        "label": "Ethereum",
        "description": "",
        "address": "0xE2E6653819dc4E5Ab2D35D12e3722E2550E9bC9e",
        "qr_url": "https://i.imgur.com/ethereum_qr.png"
    },
    "solana": {
        "label": "Solana",
        "description": "",
        "address": "2EiASQv2gv9qpVrC6L3qwZ4DnDUiozrDtATR2abSTR8x",
        "qr_url": "https://i.imgur.com/solana_qr.png"
    },
}

class PaymentSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=CRYPTO_DATA[c]["label"], description=CRYPTO_DATA[c]["description"], value=c)
            for c in CRYPTO_DATA
        ]
        super().__init__(placeholder="Select a crypto address...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        choix = self.values[0]
        data = CRYPTO_DATA[choix]
        embed = discord.Embed(
            title="💎 VIP Payment Instructions",
            description=(
                f"🚀 Ready to join the elite ? Unlock your access to the VIP zone now! \n\n 💰 Send **€200** in **{data['label']}** to the address below to activate your membership. \n\n 🔗 Address: `{data['address']}` \n\n📸 After sending, don't forget to share a screenshot of the transaction and the sender address with an admin for verification. \n"
            ),
            color=0xFF9900
        )
        embed.set_image(url=data['qr_url'])
        await interaction.response.send_message(embed=embed, ephemeral=True)

class PaymentView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(PaymentSelect())

@bot.command()
async def paiement(ctx):
    embed = discord.Embed(
        title="💎 Payment for **EARLY DROP VIP** Access",
        description="🚀 Want to be ahead of the game on every pump ? Gain exclusive access to the EARLY DROP VIP channel now ! \n\n 🔥 In this private channel, you'll get PUMP alerts before everyone else – giving you the chance to buy early and profit big. \n 💰 More speed = more gains. Simple. \n\n 🔐 To unlock access : \n 💶 Send the equivalent of `€200` in crypto to the address of your choice below. \n\n 📸 Once done, send a screenshot of the payment + the sending address to an admin to verify your access.\n\n 👇 Choose your preferred payment method below :",
        color=0xFF9900
    )
    await ctx.send(embed=embed, view=PaymentView())



####### MESSAGE
COLOR_ROYAL_BLUE = 0x4169E1  # Définition de la couleur bleue royale

@bot.command()
async def message(ctx):
    await ctx.message.delete()

    if ctx.author.id not in AUTHORIZED_USER_ID:
        try:
            await ctx.author.send("⛔ Tu n'as pas la permission d'utiliser cette commande.")
        except discord.Forbidden:
            pass
        return


    user = ctx.author

    def check(m):
        return m.author == user and isinstance(m.channel, discord.DMChannel)

    try:
        await user.send("⚙️ Envoi de message personnalisé :")

        channel_id_str = await ask_question(user, "📢 Quel est l'**ID du salon** où envoyer le message ?", check)
        if channel_id_str is None:
            return

        try:
            channel_id = int(channel_id_str)
        except ValueError:
            await user.send("❌ L'ID du salon doit être un nombre.")
            return

        message_content = await ask_question(user, "✉️ Quel est le **message** à envoyer ?", check)
        if message_content is None:
            return

        channel = bot.get_channel(channel_id)
        if channel is None:
            await user.send("❌ Salon introuvable. Assure-toi que l'ID est correct et que le bot a accès au salon.")
            return

        embed_msg = discord.Embed(description=message_content, color=COLOR_ROYAL_BLUE)
        embed_msg.set_footer(text="PUMP Signals powered by THE INSIDERS")
        await channel.send(embed=embed_msg)

        await user.send(f"✅ Message envoyé dans le salon <#{channel_id}>.")

    except discord.Forbidden:
        await ctx.send("❌ Impossible de t'envoyer un message privé. Active-les !", delete_after=10)


# Lancement du bot
token = os.getenv("TOKEN_BOT")
bot.run(MTM5NjkzODU3NzQ5MzA5ODUxNg.GOSDtx.b7tsq8x6CIrFmKKEzhxmCrj6Xy-iSoTwcg4Zxc)
