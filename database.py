import aiosqlite

#-------------------------------------------------------------------------------------------------------------------------
# Fonction pour créer une table dans la base de données si elle n'existe pas déjà
async def create_table():
    async with aiosqlite.connect('Main.db') as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                discord_id TEXT PRIMARY KEY, 
                discord_username TEXT, 
                tournament_number INT DEFAULT 0, 
                tournament_wins INT DEFAULT 0, 
                match_number INT DEFAULT 0, 
                match_wins INT DEFAULT 0
            )
        """)
        await db.commit()

#-------------------------------------------------------------------------------------------------------------------------  
# Fonction pour insérer un utilisateur dans la base de données
async def insert_data(user_id, username):
    async with aiosqlite.connect('Main.db') as db:
        await db.execute("""
            INSERT OR IGNORE INTO users (discord_id, discord_username, tournament_number, tournament_wins, match_number, match_wins) 
            VALUES (?, ?, 0, 0, 0, 0)
        """, (user_id, username))
        await db.commit()

#-------------------------------------------------------------------------------------------------------------------------
# Fonction pour récupérer le nom d'utilisateur
async def get_username(user_id):
    async with aiosqlite.connect('Main.db') as db:
        cursor = await db.execute("SELECT discord_username FROM users WHERE discord_id = ?", (user_id,))
        username = await cursor.fetchone()
        await cursor.close()
        return username[0] if username else None

#------------------------------------------------------------------------------------------------------------------------
# Fonction pour récupérer toutes les données d'un utilisateur
async def get_data(user_id):
    async with aiosqlite.connect('Main.db') as db:
        cursor = await db.execute("SELECT * FROM users WHERE discord_id = ?", (user_id,))
        data = await cursor.fetchone()
        await cursor.close()
        return data

#-------------------------------------------------------------------------------------------------------------------------
