import streamlit as st
import sqlite3
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import io
import time
import json

# Set up the Streamlit page (must be the first command)
st.set_page_config(layout="wide")  # Use the full width of the screen

# Hide Streamlit menu, footer, and prevent code inspection
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden; display: none;}
    .stDeployButton {display: none !important;}  /* Hide GitHub button */
    </style>

    <script>
    document.addEventListener('contextmenu', event => event.preventDefault());
    document.onkeydown = function(e) {
        if (e.ctrlKey && (e.keyCode === 85 || e.keyCode === 83)) {
            return false;  // Disable "Ctrl + U" (View Source) & "Ctrl + S" (Save As)
        }
        if (e.keyCode == 123) {
            return false;  // Disable "F12" (DevTools)
        }
    };
    </script>
    """, unsafe_allow_html=True)

# Custom CSS for better styling
st.markdown(
    """
    <style>
    /* General Styling */
    .block-container {
        padding-top: 0rem !important;
        padding-bottom: 0rem !important;
        margin-top: 0rem !important;
    }
    [data-testid="stHeader"] {
        display: none !important;
    }
    [data-testid="stVerticalBlock"] {
        gap: 0rem !important;
    }
    .stApp {
        margin-top: 0px !important;
    }
    [data-testid="stToolbar"] {
        display: none !important;
    }
    .stTabs {
        margin-top: 0px !important;
    }
    body {
        font-family: 'Arial', sans-serif;
        background-color: #f5f5f5;
    }
    @keyframes slide {
        0% { transform: translateX(0%); }
        100% { transform: translateX(-100%); }
    }
    /* Popup CSS */
    .popup {
        position: fixed;
        top: 20px;
        right: 20px;
        background-color: #4CAF50;
        color: white;
        padding: 15px;
        border-radius: 5px;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        z-index: 1000;
        animation: fadeInOut 3s ease-in-out;
    }
    @keyframes fadeInOut {
        0% { opacity: 0; }
        10% { opacity: 1; }
        90% { opacity: 1; }
        100% { opacity: 0; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- CONFIG ----------
# Remove this
# TEAMS = ["Team A", "Team B", "Team C", "Team D"]
# STARTING_BUDGET = 100000
BID_INCREMENT = 5000

# ---------- DB SETUP ----------
conn = sqlite3.connect('players_game.db', check_same_thread=False)
c = conn.cursor()

# Create tables
c.execute('''CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    rating INTEGER,
    category TEXT,
    nationality TEXT,
    image_url TEXT,
    base_price INTEGER,
    current_bid INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 0,
    winner_team TEXT DEFAULT NULL,
    unsold_timestamp REAL DEFAULT 0
)''')

c.execute('''CREATE TABLE IF NOT EXISTS bids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER,
    team_name TEXT,
    amount INTEGER,
    timestamp TEXT
)''')

# Create teams table with password column
c.execute('''CREATE TABLE IF NOT EXISTS teams (
    name TEXT PRIMARY KEY,
    budget_remaining INTEGER,
    logo_url TEXT,
    initial_budget INTEGER,
    password TEXT NOT NULL
)''')

# Add password column if it doesn't exist
try:
    c.execute("ALTER TABLE teams ADD COLUMN password TEXT NOT NULL DEFAULT ''")
except sqlite3.OperationalError:
    # Handle the case where the column already exists or other errors
    pass

# Check if unsold_timestamp column exists
try:
    c.execute("SELECT unsold_timestamp FROM items LIMIT 1")
except sqlite3.OperationalError:
    # Column doesn't exist, add it
    c.execute("ALTER TABLE items ADD COLUMN unsold_timestamp REAL DEFAULT 0")

# Check if current_bid column exists
try:
    c.execute("SELECT current_bid FROM items LIMIT 1")
except sqlite3.OperationalError:
    # Column doesn't exist, add it
    c.execute("ALTER TABLE items ADD COLUMN current_bid INTEGER DEFAULT 0")

# Check if previous_team column exists (for RTM)
try:
    c.execute("SELECT previous_team FROM items LIMIT 1")
except sqlite3.OperationalError:
    # Column doesn't exist, add it
    c.execute("ALTER TABLE items ADD COLUMN previous_team TEXT DEFAULT NULL")

# Check if last_activity_timestamp column exists
try:
    c.execute("SELECT last_activity_timestamp FROM items LIMIT 1")
except sqlite3.OperationalError:
    c.execute("ALTER TABLE items ADD COLUMN last_activity_timestamp REAL DEFAULT 0")

# Create sold_items table
c.execute('''CREATE TABLE IF NOT EXISTS sold_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL,
    sold_amount INTEGER,
    rating INTEGER,
    category TEXT,
    nationality TEXT,
    team_bought TEXT,
    timestamp TEXT
)''')

# Create unsold_items table
c.execute('''CREATE TABLE IF NOT EXISTS unsold_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL,
    rating INTEGER,
    category TEXT,
    nationality TEXT,
    status TEXT,
    timestamp TEXT
)''')

# Create sponsors table
c.execute('''CREATE TABLE IF NOT EXISTS sponsors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    logo_url TEXT NOT NULL
)''')

# Check if is_rtm column exists (Robust)
try:
    c.execute("ALTER TABLE sold_items ADD COLUMN is_rtm INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    # Likely column already exists
    pass

# Create global_settings table
c.execute('''CREATE TABLE IF NOT EXISTS global_settings (
    key TEXT PRIMARY KEY,
    value TEXT
)''')

conn.commit()

# Initialize global settings if empty
c.execute("SELECT COUNT(*) FROM global_settings")
if c.fetchone()[0] == 0:
    default_tiers = [
        {"limit": 10000000, "increment": 500000},    # 1Cr, 5L
        {"limit": 20000000, "increment": 1000000},   # 2Cr, 10L
        {"limit": 50000000, "increment": 2500000},   # 5Cr, 25L
        {"limit": 100000000, "increment": 5000000},  # 10Cr, 50L
        {"limit": 9990000000, "increment": 10000000} # 999Cr, 1Cr
    ]
    
    settings_defaults = {
        "max_squad_size": "25",
        "min_squad_size": "18",
        "max_overseas": "8",
        "initial_purse": "1000000000", # 100 Cr
        "bidding_tiers": json.dumps(default_tiers),
        "timing_bid_duration": "60",
        "timing_rtm_decision": "30",
        "timing_auto_break": "300",
        "rtm_max_total": "2",
        "rtm_max_indian": "1",
        "rtm_max_overseas": "1",
        "rtm_option": "true"
    }
    
    for key, val in settings_defaults.items():
        c.execute("INSERT OR IGNORE INTO global_settings (key, value) VALUES (?, ?)", (key, val))
    conn.commit()

# Initialize teams if not present
# for team in TEAMS:
#     c.execute("INSERT OR IGNORE INTO teams (name, budget_remaining) VALUES (?, ?)", (team, STARTING_BUDGET))
conn.commit()

# ---------- MIGRATION ----------
# Check if sponsors table is empty and populate it if needed
c.execute("SELECT COUNT(*) FROM sponsors")
if c.fetchone()[0] == 0:
    initial_sponsors = [
        {"name": "Jio", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/50/Reliance_Jio_Logo_%28October_2015%29.svg/500px-Reliance_Jio_Logo_%28October_2015%29.svg.png"},
        {"name": "Mobil", "logo": "https://images.seeklogo.com/logo-png/30/1/mobil-logo-png_seeklogo-302049.png"},
        {"name": "Gemini", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8a/Google_Gemini_logo.svg/500px-Google_Gemini_logo.svg.png"},
        {"name": "vivo", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e5/Vivo_mobile_logo.png/500px-Vivo_mobile_logo.png"},
        {"name": "Castrol", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/40/Castrol_logo_2023.svg/1200px-Castrol_logo_2023.svg.png"},
        {"name": "Nike", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a6/Logo_NIKE.svg/500px-Logo_NIKE.svg.png"},
        {"name": "EA", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0d/Electronic-Arts-Logo.svg/500px-Electronic-Arts-Logo.svg.png"},
        {"name": "adda52", "logo": "https://mma.prnewswire.com/media/543915/Adda52_Rummy_Logo.jpg?p=facebook"},
        {"name": "Unilever", "logo": "https://cdn-icons-png.flaticon.com/512/5977/5977593.png"},
        {"name": "Pepsi", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0f/Pepsi_logo_2014.svg/500px-Pepsi_logo_2014.svg.png"},
        {"name": "Coca-Cola", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/ce/Coca-Cola_logo.svg/500px-Coca-Cola_logo.svg.png"},
        {"name": "Adidas", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/20/Adidas_Logo.svg/500px-Adidas_Logo.svg.png"},
        {"name": "Samsung", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/61/Samsung_old_logo_before_year_2015.svg/2560px-Samsung_old_logo_before_year_2015.svg.png"},
        {"name": "Microsoft", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/96/Microsoft_logo_%282012%29.svg/500px-Microsoft_logo_%282012%29.svg.png"},
        {"name": "Amazon", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a9/Amazon_logo.svg/500px-Amazon_logo.svg.png"},
    ]
    for sponsor in initial_sponsors:
        c.execute("INSERT INTO sponsors (name, logo_url) VALUES (?, ?)", (sponsor["name"], sponsor["logo"]))
    conn.commit()

# Ensure system images exist (run this outside the empty check)
system_sponsors = [
    ("No Bidding Placeholder", "https://i.postimg.cc/rm46tZSY/Untitled-design-(2).gif"),
    ("Title Sponsor", "https://i.postimg.cc/sx5jPgR3/TITLE-SPONSOR.png")
]

for name, url in system_sponsors:
    c.execute("SELECT count(*) FROM sponsors WHERE name = ?", (name,))
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO sponsors (name, logo_url) VALUES (?, ?)", (name, url))
conn.commit()

# ---------- FUNCTIONS ----------

def get_active_item():
    c.execute("SELECT id, name, rating, category, nationality, image_url, base_price, current_bid, is_active, winner_team, unsold_timestamp, previous_team, last_activity_timestamp FROM items WHERE is_active = 1 LIMIT 1")
    return c.fetchone()

def get_highest_bid(item_id):
    c.execute("SELECT team_name, amount FROM bids WHERE item_id = ? ORDER BY amount DESC LIMIT 1", (item_id,))
    return c.fetchone()

def get_bid_increment(current_bid):
    """
    Returns bid increment based on current bid amount using dynamic tiers from DB.
    Fallback to hardcoded values if DB fails.
    """
    try:
        c.execute("SELECT value FROM global_settings WHERE key = 'bidding_tiers'")
        row = c.fetchone()
        if row:
            tiers = json.loads(row[0])
            for tier in tiers:
                if current_bid < tier['limit']:
                    return tier['increment']
            # If above all limits, use the last increment
            return tiers[-1]['increment']
            
    except Exception as e:
        print(f"Error fetching bid increments: {e}")
    
    # Fallback Logic
    if current_bid < 10000000:  # Less than ₹1 crore
        return 500000  # ₹5 lakh
    elif current_bid < 20000000:  # Less than ₹2 crore
        return 1000000  # ₹10 lakh
    elif current_bid < 50000000:  # Less than ₹5 crore
        return 2500000  # ₹25 lakh
    else:  # Above ₹5 crore
        return 5000000  # ₹50 lakh

def place_bid(item_id, team_name, current_amount):
    # Check if the item is already sold
    c.execute("SELECT winner_team, current_bid FROM items WHERE id = ?", (item_id,))
    item_details = c.fetchone()
    
    # Get the team's remaining budget
    remaining_budget = get_team_budget(team_name)

    # Check if this is the first bid
    c.execute("SELECT COUNT(*) FROM bids WHERE item_id = ?", (item_id,))
    bid_count = c.fetchone()[0]
    
    # If it's the first bid, use base price, otherwise add increment
    if bid_count == 0:
        new_amount = current_amount  # Use base price for first bid
    else:
        # Get the appropriate bid increment based on current amount
        increment = get_bid_increment(current_amount)
        new_amount = current_amount + increment

    # Check if the new bid amount exceeds the remaining budget
    if new_amount > remaining_budget:
        st.warning(f"{team_name} doesn't have enough budget to place this bid!")
        return  # Exit the function if the bid cannot be placed

    if item_details and item_details[0] != 'UNSOLD':
        previous_winner = item_details[0]
        previous_amount = item_details[1]
        
        # Refund the previous team
        update_team_budget(previous_winner, previous_amount)
        
        # Remove the item from sold_items table
        c.execute("DELETE FROM sold_items WHERE item_name = ?", (item_details[1],))

    c.execute("INSERT INTO bids (item_id, team_name, amount, timestamp) VALUES (?, ?, ?, ?)",
              (item_id, team_name, new_amount, datetime.now().isoformat()))
    # Update current_bid AND last_activity_timestamp
    current_ts = datetime.now().timestamp()
    c.execute("UPDATE items SET current_bid = ?, last_activity_timestamp = ? WHERE id = ?", (new_amount, current_ts, item_id))
    conn.commit()

def get_team_budget(team_name):
    c.execute("SELECT budget_remaining FROM teams WHERE name = ?", (team_name,))
    result = c.fetchone()
    return result[0] if result else 0

def update_team_budget(team_name, spent_amount):
    c.execute("UPDATE teams SET budget_remaining = budget_remaining - ? WHERE name = ?", (spent_amount, team_name))
    conn.commit()

def get_all_items():
    c.execute("SELECT id, name, rating, category, nationality, image_url, base_price, current_bid, is_active, winner_team, previous_team FROM items")
    return c.fetchall()

def set_active_item(item_id):
    # Set all items to inactive
    c.execute("UPDATE items SET is_active = 0 WHERE is_active = 1")
    
    refund_msg = None
    
    # --- RESET LOGIC Check ---
    # Retrieve current details to see if it was previously sold
    c.execute("SELECT winner_team, current_bid, name FROM items WHERE id = ?", (item_id,))
    row = c.fetchone()
    if row:
        prev_winner, sold_amount, item_name = row
        sold_amount = sold_amount if sold_amount is not None else 0.0
        
        # If there was a winner, we need to REFUND the budget and delete from sold_items
        if prev_winner:
            # 1. Refund Budget
            if sold_amount > 0:
                c.execute("UPDATE teams SET budget_remaining = budget_remaining + ? WHERE name = ?", (sold_amount, prev_winner))
                refund_msg = f"RESET: Refunded {format_amount(sold_amount)} to {prev_winner}"
                print(refund_msg)
            
            # 2. Remove from sold_items
            c.execute("DELETE FROM sold_items WHERE item_name = ?", (item_name,))
            # Only clear winner if we actually found one
    
    # DO NOT Clear existing bids for this item (Preserve History)
    # c.execute("DELETE FROM bids WHERE item_id = ?", (item_id,))
    
    # Calculate correct current_bid (Max of existing bids or base_price)
    c.execute("SELECT MAX(amount) FROM bids WHERE item_id = ?", (item_id,))
    res_max = c.fetchone()
    resume_bid = res_max[0] if res_max and res_max[0] else None
    
    # Set the selected item to active and reset timestamp (and clear winner)
    # Using SQLite current time to ensure freshness
    
    if resume_bid:
         # Resume from highest bid
         c.execute("UPDATE items SET is_active = 1, winner_team = NULL, current_bid = ?, last_activity_timestamp = strftime('%s', 'now') WHERE id = ?", (resume_bid, item_id))
    else:
         # Fresh start (base price)
         c.execute("UPDATE items SET is_active = 1, winner_team = NULL, current_bid = base_price, last_activity_timestamp = strftime('%s', 'now') WHERE id = ?", (item_id,))

    conn.commit()
    return refund_msg

def attempt_stop_bidding(item_id=None):
    """
    Checks RTM and finalized the sale/stop bidding.
    Returns True if flow handled (rerun needed), False if nothing happened.
    """
    active = get_active_item()
    if active:
        # Unpack appropriately (length can be 13 or 12 depending on version, checking len is safer or using *_)
        # Assuming 13 based on latest schema update
        try:
             a_id, a_name, a_rating, a_cat, a_nat, a_img, a_bp, a_bid, a_active, a_win, a_unsold, a_prev_team, a_ts = active
        except ValueError:
             # Fallback if unpacking fails
             a_id = active[0]
             a_prev_team = active[11]
        
        # Override item_id if provided (though mostly we use active item)
        if item_id and item_id != a_id:
            return False

        # Get highest bidder
        highest = get_highest_bid(a_id)
        
        if highest:
            h_team, h_amount = highest
            
            # Check RTM condition: Previous team exists AND is NOT the highest bidder
            # DEBUG
            print(f"RTM DEBUG: ActiveID={a_id}, ArgID={item_id}, Prev='{a_prev_team}', Highest='{h_team}'")
            
            # Robust Comparison: Strip whitespace and lowercase
            prev_clean = a_prev_team.strip().lower() if a_prev_team else ""
            highest_clean = h_team.strip().lower() if h_team else ""
            
            if prev_clean and prev_clean != highest_clean:
                # Check RTM Enabled
                c.execute("SELECT value FROM global_settings WHERE key = 'rtm_option'")
                res_opt = c.fetchone()
                rtm_enabled = (res_opt[0] == 'true') if res_opt else True

                if rtm_enabled:
                    # --- CHECK IF RTM LIMITS ARE ALREADY REACHED ---
                    # If blocked, we skip RTM entirely and auto-sell to highest bidder
                    
                    # 1. Check Nationality
                    # active item index 4 is nationality
                    try:
                        p_nat_chk = active[4]
                    except:
                        c.execute("SELECT nationality FROM items WHERE id=?", (a_id,))
                        p_nat_chk = c.fetchone()[0]
                    
                    is_indian_chk = (p_nat_chk == 'India')

                    # 2. Check Eligibility
                    if check_rtm_eligibility(a_prev_team, is_indian_chk):
                        st.session_state['rtm_state'] = {
                            'active': True, 
                            'item_id': a_id, 
                            'prev_team': a_prev_team, 
                            'bidder': h_team, 
                            'amount': h_amount,
                            'timestamp': datetime.now().timestamp()
                        }
                        return True
        
        # If RTM not applicable, finalize immediately
        sale_details = finalize_item_sale()
        if sale_details:
             return True
    return False

def finalize_item_sale(recipient_team=None, is_rtm=False):
    active = get_active_item()
    if active:
        item_id = active[0]
        
        # --- PREVENT DOUBLE SELLING: ATOMIC LOCK ---
        # First, try to deactivate the item atomically.
        # This ensures only ONE thread successfully "claims" the right to sell it.
        c.execute("UPDATE items SET is_active = 0 WHERE id = ? AND is_active = 1", (item_id,))
        if c.rowcount == 0:
            # Another thread already processed/sold this item
            return None
        
        # Commit the lock immediately
        conn.commit()
        # ------------------------------------------

        # Determine winner and amount
        winner, amount = None, active[7] # Default amount is current_bid
        
        if recipient_team:
             # RTM Case or forced sale
             winner = recipient_team
             # Amount is already current_bid
        else:
             # Standard highest bidder case
             highest = get_highest_bid(item_id)
             if highest:
                 winner, amount = highest
        
        if winner:
            update_team_budget(winner, amount)
            c.execute("UPDATE items SET winner_team = ? WHERE id = ?", (winner, item_id))
            
            # Insert sold item into sold_items table
            c.execute("INSERT INTO sold_items (item_name, sold_amount, rating, category, nationality, team_bought, timestamp, is_rtm) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (active[1], amount, active[2], active[3], active[4], winner, datetime.now().isoformat(), 1 if is_rtm else 0))
            
            # Remove from unsold_items table
            c.execute("DELETE FROM unsold_items WHERE item_name = ?", (active[1],))
            
            conn.commit()
            return winner, amount, active[1]  # Return sale details
        
        # If no winner (shouldn't really happen here if active but handled safely)
        # We already set is_active=0 above, so just commit
        conn.commit()
    return None

def get_team_budgets():
    c.execute("SELECT name, budget_remaining, logo_url FROM teams")
    return c.fetchall()

def mark_as_unsold(item_id):
    # Set a timestamp for when the item was marked as unsold
    timestamp = datetime.now().timestamp()
    c.execute("UPDATE items SET winner_team = 'UNSOLD', is_active = 0, unsold_timestamp = ? WHERE id = ?", 
             (timestamp, item_id))
    
    # Get item details to insert into unsold_items table
    c.execute("SELECT name, rating, category, nationality FROM items WHERE id = ?", (item_id,))
    item_details = c.fetchone()
    
    if item_details:
        c.execute("INSERT INTO unsold_items (item_name, rating, category, nationality, status, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                  (item_details[0], item_details[1], item_details[2], item_details[3], 'Unsold', datetime.now().isoformat()))
    
    conn.commit()
    return item_details[0] if item_details else None

def delete_item(item_id):
    # Fetch the item name before deletion
    c.execute("SELECT name FROM items WHERE id = ?", (item_id,))
    item_name = c.fetchone()
    
    if item_name:
        item_name = item_name[0]  # Get the actual name from the tuple

        # Delete from items table
        c.execute("DELETE FROM items WHERE id = ?", (item_id,))
        # Delete from bids table
        c.execute("DELETE FROM bids WHERE item_id = ?", (item_id,))
        # Delete from sold_items and unsold_items tables
        c.execute("DELETE FROM sold_items WHERE item_name = ?", (item_name,))
        c.execute("DELETE FROM unsold_items WHERE item_name = ?", (item_name,))
    
    conn.commit()

def get_team_squad_info(team_name):
    # Fetch players for the specified team
    c.execute("SELECT name, rating, category, nationality FROM items WHERE winner_team = ?", (team_name,))
    players = c.fetchall()

    # Initialize metrics
    total_spent = 0
    total_rating = 0
    remaining_budget = 0  # This will be fetched from the teams table
    num_batters = 0
    num_bowlers = 0
    num_allrounders = 0
    num_wicketkeepers = 0
    num_indian_players = 0
    num_foreign_players = 0

    # Calculate metrics
    for player in players:
        player_name, player_rating, player_category, player_nationality = player
        total_rating += player_rating

        # Fetch the sold amount for the player
        c.execute("SELECT sold_amount FROM sold_items WHERE item_name = ?", (player_name,))
        sold_amount_result = c.fetchone()
        if sold_amount_result:
            total_spent += sold_amount_result[0]  # Update total_spent with the sold amount

        # Count player categories
        if player_category == "Batsman":
            num_batters += 1
        elif player_category == "Bowler":
            num_bowlers += 1
        elif player_category == "Allrounder":
            num_allrounders += 1
        elif player_category == "Wicketkeeper":
            num_wicketkeepers += 1

        # Count nationality
        if player_nationality == "India":
            num_indian_players += 1
        else:
            num_foreign_players += 1

    # Fetch remaining budget for the team
    c.execute("SELECT budget_remaining FROM teams WHERE name = ?", (team_name,))
    budget_result = c.fetchone()  # Store the result in a variable
    remaining_budget = budget_result[0] if budget_result else 0  # Check the variable

    # Total number of players bought
    total_players_bought = len(players)

    return {
        "total_spent": total_spent,
        "total_rating": total_rating,
        "remaining_budget": remaining_budget,
        "num_batters": num_batters,
        "num_bowlers": num_bowlers,
        "num_allrounders": num_allrounders,
        "num_wicketkeepers": num_wicketkeepers,
        "num_indian_players": num_indian_players,
        "num_foreign_players": num_foreign_players,
        "total_players_bought": total_players_bought,
    }

def get_rtm_stats(team_name):
    """
    Returns {'total': count, 'indian': count, 'overseas': count} of RTMs used by the team.
    """
    c.execute("SELECT nationality, is_rtm FROM sold_items WHERE team_bought = ? AND is_rtm = 1", (team_name,))
    rows = c.fetchall()
    
    total = len(rows)
    indian = sum(1 for r in rows if r[0] == 'India')
    overseas = total - indian
    
    return {'total': total, 'indian': indian, 'overseas': overseas}

def check_rtm_eligibility(team_name, is_indian):
    """
    Returns True if the team is eligible to use RTM based on limits.
    """
    # 1. Get Stats and Limits
    rtm_stats_check = get_rtm_stats(team_name)
    limits_check = get_rtm_limits()
    
    # 2. Validation Logic
    if rtm_stats_check['total'] >= limits_check['total']:
        print(f"RTM SKIPPED: Total Limit Reached for {team_name}")
        return False
    elif is_indian and rtm_stats_check['indian'] >= limits_check['indian']:
        print(f"RTM SKIPPED: Indian Limit Reached for {team_name}")
        return False
    elif not is_indian and rtm_stats_check['overseas'] >= limits_check['overseas']:
        print(f"RTM SKIPPED: Overseas Limit Reached for {team_name}")
        return False
        
    return True

def get_rtm_limits():
    """Fetch RTM limits directly from DB to ensure applied rules are used."""
    c.execute("SELECT key, value FROM global_settings WHERE key IN ('rtm_max_total', 'rtm_max_indian', 'rtm_max_overseas')")
    rows = c.fetchall()
    limit_map = {k: int(v) for k, v in rows}
    return {
        'total': limit_map.get('rtm_max_total', 2),
        'indian': limit_map.get('rtm_max_indian', 1),
        'overseas': limit_map.get('rtm_max_overseas', 1)
    }

def format_amount(amount):
    """
    Format amount in lakhs (L) or crores (Cr)
    Examples:
    - 5000000 -> 50L (50 lakhs)
    - 20000000 -> 2Cr (2 crores)
    - 22500000 -> 2.25Cr (2.25 crores)
    """
    if amount >= 10000000:  # 1 crore = 10000000
        crores = amount / 10000000
        return f"₹{crores:.2f} Cr"
    else:
        lakhs = amount / 100000
        return f"₹{lakhs:.0f}L"

def get_sold_amount(item_name):
    c.execute("SELECT sold_amount FROM sold_items WHERE item_name = ?", (item_name,))
    result = c.fetchone()
    return result[0] if result else 0

def reset_all_data():
    """
    Reset all data to start fresh:
    - Clear all bids
    - Reset all items to inactive and no winner
    - Reset current_bid to base_price (preserves original base prices)
    - Clear sold_items table
    - Clear unsold_items table
    - Reset team budgets to initial budgets
    """
    try:
        # Clear all bids
        c.execute("DELETE FROM bids")
        
        # Reset all items to inactive and no winner, and reset current_bid to base_price
        c.execute("""
            UPDATE items SET 
                is_active = 0, 
                winner_team = NULL, 
                current_bid = base_price,
                unsold_timestamp = 0
        """)
        
        # Clear sold_items table
        c.execute("DELETE FROM sold_items")
        
        # Clear unsold_items table
        c.execute("DELETE FROM unsold_items")
        
        # Reset team budgets to initial budgets
        c.execute("UPDATE teams SET budget_remaining = initial_budget")
        
        # Commit all changes
        conn.commit()
        
        return True
    except Exception as e:
        print(f"Error resetting data: {e}")
        return False

def export_all_data():
    """
    Export all database data to CSV format
    Returns a dictionary with different CSV files for different data types
    """
    try:
        # Get all items data
        c.execute("SELECT id, name, rating, category, nationality, image_url, base_price, current_bid, is_active, winner_team, unsold_timestamp FROM items")
        items_data = c.fetchall()
        
        # Get all teams data
        c.execute("SELECT name, budget_remaining, logo_url, initial_budget FROM teams")
        teams_data = c.fetchall()
        
        # Get all bids data
        c.execute("SELECT id, item_id, team_name, amount, timestamp FROM bids")
        bids_data = c.fetchall()
        
        # Get all sold items data
        c.execute("SELECT id, item_name, sold_amount, rating, category, nationality, team_bought, timestamp FROM sold_items")
        sold_items_data = c.fetchall()
        
        # Get all unsold items data
        c.execute("SELECT id, item_name, rating, category, nationality, status, timestamp FROM unsold_items")
        unsold_items_data = c.fetchall()
        
        # Create DataFrames
        items_df = pd.DataFrame(items_data, columns=[
            'ID', 'Name', 'Rating', 'Category', 'Nationality', 'Image URL', 
            'Base Price', 'Current Bid', 'Is Active', 'Winner Team', 'Unsold Timestamp'
        ])
        
        teams_df = pd.DataFrame(teams_data, columns=[
            'Team Name', 'Budget Remaining', 'Logo URL', 'Initial Budget'
        ])
        
        bids_df = pd.DataFrame(bids_data, columns=[
            'Bid ID', 'Item ID', 'Team Name', 'Amount', 'Timestamp'
        ])
        
        sold_items_df = pd.DataFrame(sold_items_data, columns=[
            'ID', 'Item Name', 'Sold Amount', 'Rating', 'Category', 
            'Nationality', 'Team Bought', 'Timestamp'
        ])
        
        unsold_items_df = pd.DataFrame(unsold_items_data, columns=[
            'ID', 'Item Name', 'Rating', 'Category', 'Nationality', 'Status', 'Timestamp'
        ])
        
        # Format amounts in the DataFrames
        items_df['Base Price'] = items_df['Base Price'].apply(lambda x: format_amount(x))
        items_df['Current Bid'] = items_df['Current Bid'].apply(lambda x: format_amount(x))
        teams_df['Budget Remaining'] = teams_df['Budget Remaining'].apply(lambda x: format_amount(x))
        teams_df['Initial Budget'] = teams_df['Initial Budget'].apply(lambda x: format_amount(x))
        bids_df['Amount'] = bids_df['Amount'].apply(lambda x: format_amount(x))
        sold_items_df['Sold Amount'] = sold_items_df['Sold Amount'].apply(lambda x: format_amount(x))
        
        return {
            'items': items_df,
            'teams': teams_df,
            'bids': bids_df,
            'sold_items': sold_items_df,
            'unsold_items': unsold_items_df
        }
        
    except Exception as e:
        print(f"Error exporting data: {e}")
        return None

# ---------- SIDEBAR ADMIN ----------
st.sidebar.title("Admin Panel")
admin_password = st.sidebar.text_input("Admin Password", type="password")

# Check if the password is correct
try:
    actual_password = st.secrets["admin_password"]
except (FileNotFoundError, KeyError):
    # Fallback for when secrets are not set up (e.g. first run on cloud without config)
    # Using a secure random string to prevent access if secrets aren't set
    actual_password = "FORCE_CONFIG_OF_SECRETS_TO_LOGIN" 

if admin_password == actual_password:
    st.session_state['admin_authenticated'] = True  # Store authentication state
    st.sidebar.success("Authenticated as Admin")
else:
    if 'admin_authenticated' in st.session_state:
        st.sidebar.success("Already authenticated as Admin")
    else:
        st.sidebar.warning("Please enter the correct password.")

    # Add tabs for different admin functions
if 'admin_authenticated' in st.session_state and st.session_state['admin_authenticated']:
    admin_tab = st.sidebar.radio("Admin Functions", ["Manage Teams", "Manage Players", "Manage Sponsors", "Rules", "Activate Bidding", "Download Data", "Reset Data"])
    
    if admin_tab == "Rules":
        st.sidebar.subheader("Auction Regulations Configuration")
        
        # Initialize session state for rules if not present or if new keys are missing
        if 'rules_state' not in st.session_state or 'rtm_option' not in st.session_state['rules_state']:
            # Fetch current settings from DB
            c.execute("SELECT key, value FROM global_settings")
            rows = c.fetchall()
            settings = {k: v for k, v in rows}
            
            # Defaults
            default_max_squad = 25
            default_min_squad = 18
            default_max_overseas = 8
            default_purse = 1000000000 # 100 Cr
            default_tiers = []

            # Timing Defaults
            default_bid_duration = 60
            default_rtm_decision = 30
            default_auto_break = 300
            
            # RTM Defaults
            default_rtm_total = 2
            default_rtm_indian = 1
            default_rtm_overseas = 1
            
            # RTM Option Default
            default_rtm_option = True

            st.session_state['rules_state'] = {
                'max_squad_size': int(settings.get('max_squad_size', default_max_squad)),
                'min_squad_size': int(settings.get('min_squad_size', default_min_squad)),
                'max_overseas': int(settings.get('max_overseas', default_max_overseas)),
                'initial_purse': float(settings.get('initial_purse', default_purse)) / 10000000.0, # Convert to Cr
                'bidding_tiers': json.loads(settings.get('bidding_tiers', json.dumps(default_tiers))),
                # Timing
                'timing_bid_duration': int(settings.get('timing_bid_duration', default_bid_duration)),
                'timing_rtm_decision': int(settings.get('timing_rtm_decision', default_rtm_decision)),
                'timing_auto_break': int(settings.get('timing_auto_break', default_auto_break)),
                # RTM Limits
                'rtm_max_total': int(settings.get('rtm_max_total', default_rtm_total)),
                'rtm_max_indian': int(settings.get('rtm_max_indian', default_rtm_indian)),
                'rtm_max_overseas': int(settings.get('rtm_max_overseas', default_rtm_overseas)),
                'rtm_option': settings.get('rtm_option', 'true') == 'true'
            }
        
        rs = st.session_state['rules_state']
        
        # --- SQUAD & PURSE ---
        st.sidebar.markdown("### Squad & Purse")
        rs['max_squad_size'] = st.sidebar.number_input("Max Squad Size", value=rs['max_squad_size'])
        rs['min_squad_size'] = st.sidebar.number_input("Min Squad Size", value=rs['min_squad_size'])
        rs['max_overseas'] = st.sidebar.number_input("Max Overseas Players", value=rs['max_overseas'])
        rs['initial_purse'] = st.sidebar.number_input("Initial Purse (Cr)", value=rs['initial_purse'])
        
        # --- TIMING REGULATIONS ---
        st.sidebar.markdown("### Timing Regulations (Seconds)")
        rs['timing_bid_duration'] = st.sidebar.number_input("Bid Duration", value=rs['timing_bid_duration'])

        
        # --- RTM LIMITS ---
        st.sidebar.markdown("### RTM Limits Configuration")
        # RTM Toggle
        rs['rtm_option'] = st.sidebar.checkbox("Enable RTM (Right to Match)", value=rs['rtm_option'])
        c_rtm1, c_rtm2, c_rtm3 = st.sidebar.columns(3)
        with c_rtm1:
            rs['rtm_max_total'] = st.number_input("Total Max", value=rs['rtm_max_total'])
        with c_rtm2:
            rs['rtm_max_indian'] = st.number_input("Max Indian", value=rs['rtm_max_indian'])
        with c_rtm3:
            rs['rtm_max_overseas'] = st.number_input("Max Overseas", value=rs['rtm_max_overseas'])

        st.sidebar.markdown("### Bidding Increments (Tiered)")
        st.sidebar.info("Up To (Cr) | Increment (Cr)")
        
        tiers = rs['bidding_tiers']
        indices_to_remove = []
        
        # Display Tiers
        for i, tier in enumerate(tiers):
            limit_cr = float(tier['limit']) / 10000000.0
            inc_cr = float(tier['increment']) / 10000000.0
            
            st.sidebar.markdown(f"**Tier {i+1}**")
            c1, c2, c3 = st.sidebar.columns([4, 4, 2])
            
            with c1:
                new_limit = st.number_input("Up To", value=limit_cr, key=f"limit_{i}")
            with c2:
                new_inc = st.number_input("Inc", value=inc_cr, key=f"inc_{i}", step=0.01, format="%.2f")
            with c3:
                st.write("")
                st.write("")
                if st.button("✕", key=f"rem_tier_{i}"):
                    indices_to_remove.append(i)
            
            # Update state immediately (will be saved on Save button)
            tier['limit'] = int(new_limit * 10000000)
            tier['increment'] = int(new_inc * 10000000)
            st.sidebar.markdown("---")

        # Handle Removal
        if indices_to_remove:
            for i in sorted(indices_to_remove, reverse=True):
                del tiers[i]
            st.rerun()

        # Add Tier
        if st.sidebar.button("+ Add Pricing Tier"):
            tiers.append({"limit": 0, "increment": 0})
            st.rerun()

        # Save Logic
        if st.sidebar.button("Save Regulations", type="primary"):
            try:
                # Prepare data for DB
                db_values = [
                    ('max_squad_size', str(rs['max_squad_size'])),
                    ('min_squad_size', str(rs['min_squad_size'])),
                    ('max_overseas', str(rs['max_overseas'])),
                    ('initial_purse', str(int(rs['initial_purse'] * 10000000))),
                    ('bidding_tiers', json.dumps(tiers)),
                    ('timing_bid_duration', str(rs['timing_bid_duration'])),

                    ('rtm_max_total', str(rs['rtm_max_total'])),
                    ('rtm_max_indian', str(rs['rtm_max_indian'])),
                    ('rtm_max_overseas', str(rs['rtm_max_overseas'])),
                    ('rtm_option', 'true' if rs['rtm_option'] else 'false')
                ]
                
                for key, val in db_values:
                    c.execute("INSERT OR REPLACE INTO global_settings (key, value) VALUES (?, ?)", (key, val))
                conn.commit()
                st.sidebar.success("Regulations Saved Successfully!")
                
                # Update session state to reflect saved (good practice)
                # (Active state is already updated, just need to persist)
                
            except Exception as e:
                st.sidebar.error(f"Error saving regulations: {e}")

    if admin_tab == "Manage Teams":
        st.sidebar.subheader("Team Management")
        
        # Add Clear All Teams button
        if st.sidebar.button("🗑️ Clear All Teams", type="primary"):
            c.execute("DELETE FROM teams")
            conn.commit()
            st.sidebar.success("All teams have been removed.")
            st.rerun()
        
        # Add new team section
        st.sidebar.markdown("### Add New Team")
        new_team_name = st.sidebar.text_input("Team Name")
        team_budget = st.sidebar.number_input("Initial Budget", min_value=0, value=100000)
        team_logo_url = st.sidebar.text_input("Team Logo URL")
        team_password = st.sidebar.text_input("Team Password", type="password")  # New password input

        if st.sidebar.button("Add Team") and new_team_name and team_password:
            c.execute("INSERT OR REPLACE INTO teams (name, budget_remaining, logo_url, initial_budget, password) VALUES (?, ?, ?, ?, ?)",
                      (new_team_name, team_budget, team_logo_url, team_budget, team_password))
            conn.commit()
            st.sidebar.success(f"Team '{new_team_name}' added/updated with the specified password.")
        
        # Show existing teams
        st.sidebar.markdown("### Existing Teams")
        # Included password in the SELECT query
        c.execute("SELECT name, budget_remaining, logo_url, initial_budget, password FROM teams")
        teams = c.fetchall()

        for team in teams:
            with st.sidebar.expander(f"Team: {team[0]}"):
                # Convert budget to crores
                current_budget = team[1] / 10000000  # Convert to crores
                initial_budget = team[3] / 10000000  # Convert to crores
                
                # Format the budget display
                budget_display = f"₹{current_budget:.2f} Cr"  # Format to two decimal places
                
                st.write(f"Current Budget: {budget_display}")
                st.write(f"Initial Budget: ₹{initial_budget:.2f} Cr")
                
                # Input fields for editing budget, logo, and password
                new_budget = st.number_input(f"Edit Budget for {team[0]}", min_value=0.0, value=max(0.0, current_budget), format="%.2f")
                new_logo_url = st.text_input(f"Edit Logo URL for {team[0]}", value=team[2])
                new_password = st.text_input(f"Edit Password for {team[0]}", value=team[4], type="password")
                
                if st.button(f"Update {team[0]}", key=f"update_{team[0]}"):
                    # Update the team in the database including password
                    c.execute("UPDATE teams SET budget_remaining = ?, logo_url = ?, password = ? WHERE name = ?", 
                              (new_budget * 10000000, new_logo_url, new_password, team[0]))
                    conn.commit()
                    st.success(f"Updated details for {team[0]}.")
                    st.rerun()
                if st.button(f"Delete {team[0]}", key=f"del_{team[0]}"):
                    c.execute("DELETE FROM teams WHERE name = ?", (team[0],))
                    conn.commit()
                    st.rerun()
    
    elif admin_tab == "Manage Players":
        st.sidebar.subheader("Player Management")
        
        # Fetch team names for RTM dropdown
        c.execute("SELECT name FROM teams")
        team_rows = c.fetchall()
        rtm_team_options = ["None"] + [row[0] for row in team_rows]

        # --- Add New Player ---
        with st.sidebar.expander("➕ Add New Player", expanded=False):
            item_name = st.text_input("New Item Name")
            item_rating = st.text_input("Player Rating", value="50")
            item_category = st.selectbox("Player Specialization", ["Batsman", "Bowler", "Allrounder", "Wicketkeeper"])
            item_nationality = st.selectbox("Player Nationality", ["India", "Afghanistan", "Australia", "Bangladesh", "England","New Zealand", "Sri Lanka", "South Africa","West Indies", "Other"])
            item_image_url = st.text_input("Player Image URL")
            
            # RTM / Previous Team Selection
            item_previous_team = st.selectbox("Previous Team (RTM)", rtm_team_options)
            if item_previous_team == "None":
                item_previous_team = None

            # Change the base price input to be in lakhs
            item_base_price = st.number_input("Base Price (in Lakhs)", min_value=0.0, value=5.0, format="%.2f")

            if st.button("Add Item") and item_name:
                try:
                    item_rating_value = int(item_rating)
                    # Convert base price from lakhs to actual amount
                    base_price_amount = int(item_base_price * 100000)
                    
                    c.execute("INSERT INTO items (name, rating, category, nationality, image_url, base_price, previous_team) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (item_name, item_rating_value, item_category, item_nationality, item_image_url, base_price_amount, item_previous_team))
                    conn.commit()
                    formatted_base_price = format_amount(base_price_amount)
                    st.success(f"Item '{item_name}' added with base price of {formatted_base_price}.")
                except ValueError:
                    st.error("Please enter a valid integer for the Player Rating.")

        # --- Edit/Delete Existing Player ---
        st.sidebar.markdown("### ✏️ Edit / Delete Player")
        
        # Fetch all players for the dropdown
        c.execute("SELECT id, name, rating, category, nationality, image_url, base_price, previous_team FROM items ORDER BY name")
        all_players = c.fetchall()
        
        player_options = {f"{p[1]} (ID: {p[0]})": p for p in all_players}
        
        selected_player_label = st.sidebar.selectbox("Select Player to Edit", [""] + list(player_options.keys()))
        
        if selected_player_label and selected_player_label != "":
            player_data = player_options[selected_player_label]
            p_id, p_name, p_rating, p_category, p_nationality, p_image, p_base_price, p_previous_team = player_data
            
            with st.sidebar.form(key=f"edit_form_{p_id}"):
                edit_name = st.text_input("Name", value=p_name)
                edit_rating = st.text_input("Rating", value=str(p_rating))
                
                categories = ["Batsman", "Bowler", "Allrounder", "Wicketkeeper"]
                cat_index = categories.index(p_category) if p_category in categories else 0
                edit_category = st.selectbox("Specialization", categories, index=cat_index)
                
                nationalities = ["India", "Afghanistan", "Australia", "Bangladesh", "England","New Zealand", "Sri Lanka", "South Africa","West Indies", "Other"]
                nat_index = nationalities.index(p_nationality) if p_nationality in nationalities else 0
                edit_nationality = st.selectbox("Nationality", nationalities, index=nat_index)
                
                edit_image = st.text_input("Image URL", value=p_image)

                # Previous Team (RTM)
                current_rtm_index = 0
                if p_previous_team and p_previous_team in rtm_team_options:
                    current_rtm_index = rtm_team_options.index(p_previous_team)
                edit_previous_team_val = st.selectbox("Previous Team (RTM)", rtm_team_options, index=current_rtm_index)
                edit_previous_team = None if edit_previous_team_val == "None" else edit_previous_team_val
                
                # Convert base price to Lakhs for display
                price_in_lakhs = float(p_base_price) / 100000.0
                edit_base_price = st.number_input("Base Price (Lakhs)", min_value=0.0, value=price_in_lakhs, format="%.2f")
                
                col1, col2 = st.columns(2)
                with col1:
                    update_submitted = st.form_submit_button("Update Player")
                with col2:
                    # Form submit buttons can't be easily distinguished for delete logic without a workaround or separating them.
                    pass
            
            # Handling Update
            if update_submitted:
                try:
                    new_rating_val = int(edit_rating)
                    new_price_val = int(edit_base_price * 100000)
                    
                    c.execute("""UPDATE items SET 
                                name=?, rating=?, category=?, nationality=?, image_url=?, base_price=?, previous_team=?
                                WHERE id=?""", 
                                (edit_name, new_rating_val, edit_category, edit_nationality, edit_image, new_price_val, edit_previous_team, p_id))
                    conn.commit()
                    st.sidebar.success(f"Player '{edit_name}' updated successfully!")
                    st.rerun()
                except ValueError:
                    st.sidebar.error("Invalid input for Rating")

            # Handling Delete (Outside Form to be safe and distinct)
            if st.sidebar.button(f"🗑️ Delete {p_name}", key=f"del_btn_{p_id}", type="primary"):
                 delete_item(p_id)
                 st.sidebar.success(f"Player '{p_name}' deleted!")
                 st.rerun()


    elif admin_tab == "Manage Sponsors":
        st.sidebar.subheader("Sponsor Management")
        
        # Add new sponsor
        st.sidebar.markdown("### Add New Sponsor")
        new_sponsor_name = st.sidebar.text_input("Sponsor Name")
        new_sponsor_logo = st.sidebar.text_input("Sponsor Logo URL")
        
        if st.sidebar.button("Add Sponsor") and new_sponsor_name and new_sponsor_logo:
            c.execute("INSERT INTO sponsors (name, logo_url) VALUES (?, ?)", (new_sponsor_name, new_sponsor_logo))
            conn.commit()
            st.sidebar.success(f"Sponsor '{new_sponsor_name}' added.")
            
        # List and delete sponsors
        st.sidebar.markdown("### Existing Sponsors")
        c.execute("SELECT id, name, logo_url FROM sponsors")
        sponsors = c.fetchall()
        
        for sponsor in sponsors:
            with st.sidebar.expander(f"{sponsor[1]}"):
                st.image(sponsor[2], width=100)
                
                # Update fields
                new_name = st.text_input("Name", value=sponsor[1], key=f"name_{sponsor[0]}")
                new_logo = st.text_input("Logo URL", value=sponsor[2], key=f"logo_{sponsor[0]}")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Update", key=f"upd_{sponsor[0]}"):
                        c.execute("UPDATE sponsors SET name = ?, logo_url = ? WHERE id = ?", (new_name, new_logo, sponsor[0]))
                        conn.commit()
                        st.success("Updated!")
                        st.rerun()
                with col2:
                    if st.button("Delete", key=f"del_{sponsor[0]}"):
                        c.execute("DELETE FROM sponsors WHERE id = ?", (sponsor[0],))
                        conn.commit()
                        st.rerun()

    elif admin_tab == "Activate Bidding":
        st.sidebar.subheader("Activate Bidding")
        items = get_all_items()
        item_names = [item[1] for item in items]
        selected_item_name = st.sidebar.selectbox("Select Player to Activate Bidding", item_names)

        if selected_item_name:
            selected_item = next(item for item in items if item[1] == selected_item_name)
            
            # Show RTM info
            # Index 10 is 'previous_team' in get_all_items() query
            rtm_holder = selected_item[10] if len(selected_item) > 10 else "Unknown"
            
            # Check global RTM setting
            rtm_enabled_admin = True
            try:
                c.execute("SELECT value FROM global_settings WHERE key = 'rtm_option'")
                row_opt_admin = c.fetchone()
                if row_opt_admin:
                    rtm_enabled_admin = (row_opt_admin[0] == 'true')
            except Exception:
                pass

            # Check Team Eligibility (Limits)
            is_rtm_eligible_admin = True
            
            # Ensure we have a valid team to be an RTM holder
            has_valid_holder = rtm_holder and rtm_holder != "Unknown" and rtm_holder != "None"
            
            if has_valid_holder:
                 # Index 4 is nationality
                 p_nat_adm = selected_item[4]
                 is_ind_adm = (p_nat_adm == 'India')
                 # Use our helper
                 if not check_rtm_eligibility(rtm_holder, is_ind_adm):
                     is_rtm_eligible_admin = False
            else:
                is_rtm_eligible_admin = False

            if rtm_enabled_admin and is_rtm_eligible_admin and has_valid_holder:
                st.sidebar.info(f"RTM Holder: {rtm_holder}")
            else:
                p_text = rtm_holder if has_valid_holder else "NA"
                st.sidebar.info(f"Previous Team: {p_text}")
            
            # Delete button
            if st.sidebar.button("🗑️ Delete Player", type="primary"):
                delete_item(selected_item[0])
                st.sidebar.success(f"Player '{selected_item_name}' deleted.")
                st.rerun()
            
            # Unsold button
            if st.sidebar.button("❌ Mark as Unsold", type="secondary"):
                unsold_item_name = mark_as_unsold(selected_item[0])
                
                if unsold_item_name:
                    st.sidebar.success(f"Player '{selected_item_name}' marked as unsold.")
                    st.rerun()
            
            if st.sidebar.button("Start Bidding"):
                refund_feedback = set_active_item(selected_item[0])
                st.session_state['rtm_state'] = {'active': False, 'item_id': None, 'prev_team': None, 'bidder': None, 'amount': 0}
                st.session_state['force_rtm_reset'] = True
                if refund_feedback:
                     st.session_state['refund_message'] = refund_feedback
                st.sidebar.success(f"Bidding started for '{selected_item_name}'")
                st.rerun()

            # --- RTM LOGIC STATUS ---
            if 'rtm_state' not in st.session_state:
                st.session_state['rtm_state'] = {'active': False, 'item_id': None, 'prev_team': None, 'bidder': None, 'amount': 0}

            # Stop Bidding Button
            if st.sidebar.button("Stop Current Bidding"):
                 if attempt_stop_bidding():
                     st.sidebar.success("Bidding stopped / RTM Triggered.")
                     st.rerun()

            # RTM Prompt (Only show if RTM is active for the SELECTED item)
            current_active_id = selected_item[0]
            
            # --- STALE RTM CHECK ---
            # If RTM is locally active, check if the item is ACTUALLY still active in DB.
            # If it's sold (is_active=0), then RTM is done, hide the alert.
            if st.session_state.get('rtm_state', {}).get('active'):
                 rtm_chk_id = st.session_state['rtm_state'].get('item_id')
                 if rtm_chk_id:
                     c.execute("SELECT is_active FROM items WHERE id = ?", (rtm_chk_id,))
                     chk_res = c.fetchone()
                     if chk_res and chk_res[0] == 0:
                          st.session_state['rtm_state']['active'] = False
                          st.rerun()
            # -----------------------

            if st.session_state['rtm_state']['active'] and st.session_state['rtm_state'].get('item_id') == current_active_id:
                 rtm = st.session_state['rtm_state']
                 st.sidebar.markdown("---")
                 st.sidebar.warning(f"🔔 **RTM ALERT**")
                 st.sidebar.write(f"Previous Team: **{rtm['prev_team']}**")
                 st.sidebar.write(f"Highest Bid: **{format_amount(rtm['amount'])}** by **{rtm['bidder']}**")
                 st.sidebar.write("Does the Previous Team want to exercise RTM?")
                 
                 col_rtm1, col_rtm2 = st.sidebar.columns(2)
                 
                 if col_rtm1.button("✅ Yes, Retain"):
                     # Check budget of previous team
                     prev_team_budget = get_team_budget(rtm['prev_team'])
                     
                     # Enforce RTM Limits Check
                     rtm_stats_admin = get_rtm_stats(rtm['prev_team'])
                     
                     # Get Max Limits from DB
                     limits_admin = get_rtm_limits()
                     limit_total_admin = limits_admin['total']
                     limit_indian_admin = limits_admin['indian']
                     limit_overseas_admin = limits_admin['overseas']

                     # Get Player Nationality

                     # Get Player Nationality
                     c.execute("SELECT nationality FROM items WHERE id = ?", (rtm['item_id'],))
                     res_nat = c.fetchone()
                     p_nat_admin = res_nat[0] if res_nat else "Unknown"
                     is_indian_admin = (p_nat_admin == 'India')

                     limit_error = None
                     if rtm_stats_admin['total'] >= limit_total_admin:
                         limit_error = "Total RTM Limit Reached!"
                     elif is_indian_admin and rtm_stats_admin['indian'] >= limit_indian_admin:
                         limit_error = "Indian RTM Limit Reached!"
                     elif not is_indian_admin and rtm_stats_admin['overseas'] >= limit_overseas_admin:
                         limit_error = "Overseas RTM Limit Reached!"

                     if limit_error:
                          st.sidebar.error(limit_error)
                     elif prev_team_budget >= rtm['amount']:
                         finalize_item_sale(recipient_team=rtm['prev_team'], is_rtm=True)
                         st.session_state['rtm_state']['active'] = False
                         st.sidebar.success(f"Player sold to {rtm['prev_team']} via RTM!")
                         st.rerun()
                     else:
                         st.sidebar.error(f"{rtm['prev_team']} does not have enough budget ({format_amount(prev_team_budget)})")

                 if col_rtm2.button("❌ No, Decline"):
                     finalize_item_sale() # Sell to original highest bidder
                     st.session_state['rtm_state']['active'] = False
                     st.sidebar.info(f"RTM Declined. Player sold to {rtm['bidder']}.")
                     st.rerun()

        # Sponsor Logo
        c.execute("SELECT logo_url FROM sponsors WHERE name = 'Title Sponsor'")
        title_sponsor = c.fetchone()
        if title_sponsor:
            st.sidebar.markdown(f'<div style="margin-top: 20px; display: flex; justify-content: center;"><img src="{title_sponsor[0]}" width="1500" style="object-fit: contain;"></div>', unsafe_allow_html=True)

    elif admin_tab == "Download Data":
        st.sidebar.subheader("Download Database Data")
        st.sidebar.info("📊 Export all auction data to CSV files")
        
        # Initialize session state for download data
        if 'download_data' not in st.session_state:
            st.session_state['download_data'] = None
        if 'download_timestamp' not in st.session_state:
            st.session_state['download_timestamp'] = None
        
        # Download button
        if st.sidebar.button("📥 Download All Data", type="primary"):
            with st.spinner("Preparing data for download..."):
                data = export_all_data()
                
                if data:
                    # Create a zip-like structure with multiple CSV files
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    
                    # Convert DataFrames to CSV strings
                    csv_data = {}
                    for key, df in data.items():
                        csv_buffer = io.StringIO()
                        df.to_csv(csv_buffer, index=False)
                        csv_data[key] = csv_buffer.getvalue()
                    
                    # Store in session state
                    st.session_state['download_data'] = csv_data
                    st.session_state['download_timestamp'] = timestamp
                    st.sidebar.success("✅ Data prepared successfully!")
                else:
                    st.sidebar.error("❌ Failed to prepare data for download.")
        
        # Show download buttons if data is available
        if st.session_state['download_data'] and st.session_state['download_timestamp']:
            csv_data = st.session_state['download_data']
            timestamp = st.session_state['download_timestamp']
            
            st.sidebar.markdown("### Download Options:")
            
            # Items data
            st.sidebar.download_button(
                label="📋 Download Items Data",
                data=csv_data['items'],
                file_name=f"auction_items_{timestamp}.csv",
                mime="text/csv",
                help="All players/items in the database"
            )
            
            # Teams data
            st.sidebar.download_button(
                label="👥 Download Teams Data",
                data=csv_data['teams'],
                file_name=f"auction_teams_{timestamp}.csv",
                mime="text/csv",
                help="All teams and their budgets"
            )
            
            # Bids data
            st.sidebar.download_button(
                label="💰 Download Bids Data",
                data=csv_data['bids'],
                file_name=f"auction_bids_{timestamp}.csv",
                mime="text/csv",
                help="All bidding history"
            )
            
            # Sold items data
            st.sidebar.download_button(
                label="✅ Download Sold Items Data",
                data=csv_data['sold_items'],
                file_name=f"auction_sold_items_{timestamp}.csv",
                mime="text/csv",
                help="All successfully sold players"
            )
            
            # Unsold items data
            st.sidebar.download_button(
                label="❌ Download Unsold Items Data",
                data=csv_data['unsold_items'],
                file_name=f"auction_unsold_items_{timestamp}.csv",
                mime="text/csv",
                help="All unsold players"
            )
            
            # Combined data download
            combined_csv = "\n\n".join([
                f"=== {key.upper().replace('_', ' ')} DATA ===\n{csv_data[key]}" 
                for key in ['items', 'teams', 'bids', 'sold_items', 'unsold_items']
            ])
            
            st.sidebar.download_button(
                label="📦 Download Complete Data",
                data=combined_csv,
                file_name=f"auction_complete_data_{timestamp}.csv",
                mime="text/csv",
                help="All data combined in one file"
            )
            
            # Clear data button
            if st.sidebar.button("🗑️ Clear Download Data", type="secondary"):
                st.session_state['download_data'] = None
                st.session_state['download_timestamp'] = None
                st.sidebar.info("Download data cleared.")
                st.rerun()
        
        # Show data summary
        st.sidebar.markdown("### Data Summary:")
        try:
            c.execute("SELECT COUNT(*) FROM items")
            items_count = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM teams")
            teams_count = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM bids")
            bids_count = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM sold_items")
            sold_count = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM unsold_items")
            unsold_count = c.fetchone()[0]
            
            st.sidebar.markdown(f"- 📋 **Items:** {items_count}")
            st.sidebar.markdown(f"- 👥 **Teams:** {teams_count}")
            st.sidebar.markdown(f"- 💰 **Bids:** {bids_count}")
            st.sidebar.markdown(f"- ✅ **Sold Items:** {sold_count}")
            st.sidebar.markdown(f"- ❌ **Unsold Items:** {unsold_count}")
            
        except Exception as e:
            st.sidebar.error("Could not fetch data summary.")
    
    elif admin_tab == "Reset Data":
        st.sidebar.subheader("Reset All Data")
        st.sidebar.warning("⚠️ This will reset everything to start fresh!")
        
        # Add confirmation checkbox
        confirm_reset = st.sidebar.checkbox("I understand this will delete all data", key="confirm_reset")
        
        # Add reset button with confirmation
        if st.sidebar.button("🔄 Reset All Data", type="primary", disabled=not confirm_reset):
            if confirm_reset:
                if reset_all_data():
                    st.sidebar.success("✅ All data has been reset successfully!")
                    st.sidebar.info("🔄 The auction can now start fresh.")
                    st.rerun()
                else:
                    st.sidebar.error("❌ Failed to reset data. Please try again.")
            else:
                st.sidebar.warning("Please confirm that you understand the consequences.")
        
        # Show what will be reset
        st.sidebar.markdown("### What will be reset:")
        st.sidebar.markdown("- 🗑️ All bids will be cleared")
        st.sidebar.markdown("- 🔄 All players will be reset to unsold")
        st.sidebar.markdown("- 💰 Current bids will be reset to base prices")
        st.sidebar.markdown("- 💰 Team budgets will be restored to initial amounts")
        st.sidebar.markdown("- 📊 All auction history will be cleared")
        st.sidebar.markdown("- ⏹️ All active bidding will be stopped")

# ---------- MAIN UI ----------

# 🌀 Refresh page every second
st_autorefresh(interval=1000, key="refresh")

# Add custom CSS to make the app use full width and improve image styles
st.markdown("""
    <style>
        .main > div {
            max-width: 100%;
            padding-left: 5%;
            padding-right: 5%;
        }
        
        /* Team Grid Styles */
        .team-grid {
            display: flex;
            flex-direction: row;
            gap: 5px;  /* Reduced from 10px */
            padding: 0px;  /* Reduced from 10px */
            justify-content: center;  /* Center the cards */
            flex-wrap: wrap;
            margin: -5px;  /* Negative margin to offset padding */
        }
        .team-card {
            text-align: center;
            background: white;
            padding: 12px 10px 10px 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 8px;
            transition: all 0.3s cubic-bezier(.4,0,.2,1);
            position: relative;
            border-radius: 16px;
            border: 1.5px solid rgba(0,0,0,0.07);
            min-width: 80px;
            min-height: 120px;
        }
        .team-card:hover {
            transform: translateY(-4px) scale(1.04);
            box-shadow: 0 8px 24px rgba(26,115,232,0.10), 0 2px 8px rgba(0,0,0,0.10);
            border-color: #1a73e8;
        }
        .team-card img {
            width: 70px;
            height: 70px;
            object-fit: contain;
            border-radius: 12px;
            background: linear-gradient(145deg, #f8fafc 60%, #e3f0ff 100%);
            box-shadow: 0 2px 12px rgba(26,115,232,0.07);
            margin-bottom: 2px;
            margin-top: 2px;
            transition: transform 0.35s cubic-bezier(.4,0,.2,1), box-shadow 0.35s cubic-bezier(.4,0,.2,1);
        }
        .team-card:hover img {
            transform: scale(1.13) rotate(2deg);
            box-shadow: 0 8px 32px 0 rgba(26,115,232,0.18), 0 2px 8px rgba(0,0,0,0.10);
        }
        .team-name {
            font-size: 14px;  /* Reduced from 16px */
            font-weight: 800;
            color: #2c3e50;
            margin: 0;
            transition: color 0.3s ease;
        }
        .team-card:hover .team-name {
            color: #1a73e8;
        }
        .team-budget {
            font-size: 15px;
            font-weight: 900;
            color: #1a73e8;
            margin: 0;
            margin-top: 2px;
            margin-bottom: 2px;
            background: rgba(26,115,232,0.10);
            padding: 6px 7px;
            border-radius: 8px;
            letter-spacing: 0.5px;
            box-shadow: 0 1px 4px rgba(26,115,232,0.07);
            transition: all 0.3s cubic-bezier(.4,0,.2,1);
            display: inline-block;
            white-space: nowrap;
        }
        .team-card:hover .team-budget {
            transform: scale(1.08);
            color: #28a745;
            background: rgba(40,167,69,0.13);
            box-shadow: 0 2px 8px rgba(40,167,69,0.10);
        }

        /* Tab Styling */
        .stTabs {
            background: white;
            padding: 10px;
            border-radius: 15px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            margin-top: -30px !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
            background: #f8f9fa;
            padding: 10px;
            border-radius: 12px;
            border: 1px solid rgba(0,0,0,0.05);
        }
        .stTabs [data-baseweb="tab"] {
            height: 40px;
            padding: 0 20px;
            background: white;
            border-radius: 10px;
            color: #6c757d;
            font-weight: 500;
            transition: all 0.3s ease;
            border: 1px solid rgba(108,117,125,0.1);
            font-size: 14px;
        }
        .stTabs [data-baseweb="tab"]:hover {
            background: #f1f8ff;
            color: #1a73e8;
            transform: translateY(-1px);
            border-color: rgba(26,115,232,0.2);
        }
        .stTabs [aria-selected="true"] {
            background: #1a73e8 !important;
            color: white !important;
            font-weight: 600 !important;
            border-color: transparent !important;
            box-shadow: 0 2px 5px rgba(26,115,232,0.2);
        }
        
        /* Add subtle animation for tab content */
        .stTabContent {
            animation: fadeIn 0.3s ease-in-out;
        }
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(5px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
    </style>
    """, unsafe_allow_html=True)

# Fetch available teams from the database
c.execute("SELECT name, budget_remaining, password FROM teams")
available_teams = c.fetchall()

# Create a list of team names
team_names = [team[0] for team in available_teams]

# Create tabs for different sections
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🎯 Bidding & Budgets", 
    "📊 Players Market", 
    "👥 Team Squad", 
    "📜 Auction History",
    "🌟 Special Bidding Zone"  # New tab
])

# Tab 1: Bidding & Budgets
with tab1:
    st.subheader("Team Budgets")
    team_budgets = get_team_budgets()
    cols = st.columns(len(team_budgets)) if team_budgets else st.columns(1)

    # Display teams in a grid
    st.markdown('<div class="team-grid">', unsafe_allow_html=True)
    for idx, (team, budget, logo_url) in enumerate(team_budgets):
        with cols[idx]:
            st.markdown(
                f"""
                <div class=\"team-card\">
                    <img src=\"{logo_url}\" alt=\"{team} logo\" />
                    <div class=\"team-name\">{team}</div>
                    <div class=\"team-budget\">{format_amount(budget)}</div>
                </div>
                """,
                unsafe_allow_html=True
            )
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Premium Grid CSS
    st.markdown("""
        <style>
        .team-grid {
            display: contents; /* Let columns handle layout */
        }
        .team-card {
            background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
            border-radius: 16px;
            padding: 12px 8px;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.02);
            border: 1px solid rgba(255,255,255,0.8);
            transition: all 0.2s ease;
            height: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }
        .team-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 15px rgba(0,0,0,0.06);
            border-color: #cbd5e1;
        }
        .team-card img {
            width: 48px;
            height: 48px;
            object-fit: contain;
            margin-bottom: 8px;
            filter: drop-shadow(0 2px 4px rgba(0,0,0,0.1));
        }
        .team-name {
            font-size: 13px;
            font-weight: 700;
            color: #475569;
            margin-bottom: 4px;
            font-family: 'Inter', sans-serif;
        }
        .team-budget {
            font-size: 14px;
            font-weight: 700;
            color: #0f172a;
            background: rgba(15, 23, 42, 0.05);
            padding: 4px 10px;
            border-radius: 20px;
            font-family: 'Inter', sans-serif;
        }
        </style>
    """, unsafe_allow_html=True)

    # --- SLIDER MARQUEE SECTION ---
    # Fetch all bought players (winner_team not NULL or 'UNSOLD')
    c.execute("SELECT name, rating, nationality, winner_team FROM items WHERE winner_team IS NOT NULL AND winner_team != 'UNSOLD'")
    slider_players = c.fetchall()

    # Fetch team ratings (sum of player ratings per team)
    c.execute("SELECT winner_team, SUM(rating) FROM items WHERE winner_team IS NOT NULL GROUP BY winner_team")
    team_ratings_rows = c.fetchall()
    team_ratings = {row[0]: row[1] or 0 for row in team_ratings_rows}

    slider_items = []
    for name, rating, nationality, team in slider_players:
        plane = "✈️" if nationality != "India" else ""
        total_team_rating = team_ratings.get(team, 0)
        slider_items.append(f'<div class="slider-item"><span class="player-name">{name}</span> {plane} <span class="player-rating">R{rating}</span> <span class="separator">|</span> <span class="team-tag">{team}</span> <span class="team-score">({total_team_rating})</span></div>')

    if not slider_items:
        slider_html = '<div class="slider-item">No players have been bought yet.</div>'
    else:
        # Repeat to fill the marquee
        max_repeats = 200 // max(1, len(slider_items))
        repeated = slider_items * max(max_repeats, 10) # Ensure plenty of repetition
        slider_html = ''.join(repeated)

    # Add the slider CSS and HTML
    st.markdown('''
        <style>
        .slider-container {
            width: 100%;
            overflow: hidden;
            white-space: nowrap;
            background: linear-gradient(to right, #0f172a, #1e293b); /* Dark Premium Background */
            color: white;
            padding: 12px 0;
            border-radius: 12px;
            margin-bottom: 24px;
            margin-top: 24px;
            position: relative;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            border: 1px solid #334155;
            display: flex;
            align-items: center;
        }
        
        .slider-content {
            display: inline-flex;
            gap: 20px;
            padding-left: 100vw; /* Start off-screen */
            animation: slider-marquee 1800s linear infinite; /* Adjusted speed */
            align-items: center;
        }
        
        .slider-content:hover {
            animation-play-state: paused;
        }

        .slider-item {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(255, 255, 255, 0.1);
            padding: 6px 16px;
            border-radius: 50px; /* Pill shape */
            border: 1px solid rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(4px);
            color: #f8fafc;
            font-family: 'Inter', sans-serif;
            font-size: 14px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            white-space: nowrap;
        }

        .player-name {
            font-weight: 700;
            color: #ffffff;
        }

        .player-rating {
            background: #22c55e;
            color: black;
            font-size: 11px;
            font-weight: 800;
            padding: 1px 6px;
            border-radius: 10px;
        }

        .separator {
            color: #64748b;
            font-size: 12px;
        }

        .team-tag {
            color: #60a5fa; /* Light Blue */
            font-weight: 700;
        }

        .team-score {
            color: #94a3b8;
            font-size: 12px;
        }

        @keyframes slider-marquee {
            0% { transform: translateX(0); }
            100% { transform: translateX(-100%); }
        }
        </style>
        <div class="slider-container">
            <div class="slider-content">''' + slider_html + '''</div>
        </div>
    ''', unsafe_allow_html=True)
    # --- END SLIDER MARQUEE SECTION ---

    # --- RECENT 5 PLAYERS PANEL ---
    recent_players = []
    # Fetch the current active item
    active_item = get_active_item()
    if active_item:
        item_id, item_name, item_rating, item_category, item_nationality, item_image_url, item_base_price, current_bid, is_active, winner, unsold_timestamp, previous_team, last_activity_ts = active_item
        # Check if bidding is ongoing (no winner yet)
        c.execute("SELECT winner_team FROM items WHERE id = ?", (item_id,))
        winner_team = c.fetchone()[0]
        if winner_team is None:
            recent_players.append({
                'name': item_name,
                'status': 'bidding',
                'icon': '🔨',
                'amount': None,
                'team': None
            })
    # Fetch the last 4 finished bids (sold)
    c.execute("SELECT item_name, sold_amount, team_bought, timestamp FROM sold_items ORDER BY timestamp DESC LIMIT 4")
    sold = c.fetchall()

    # Fetch the last 4 unsold items
    c.execute("SELECT item_name, timestamp FROM unsold_items ORDER BY timestamp DESC LIMIT 4")
    unsold = c.fetchall()

    # Merge and sort by timestamp (most recent first)
    merged = []
    for s in sold:
        formatted_amount = format_amount(s[1])  # Format the sold amount
        merged.append({'name': s[0], 'status': 'sold', 'icon': '✅', 'amount': formatted_amount, 'team': s[2], 'ts': s[3]})
    for u in unsold:
        merged.append({'name': u[0], 'status': 'unsold', 'icon': '❌', 'amount': None, 'team': None, 'ts': u[1]})

    # Sort the merged list by timestamp
    merged = sorted(merged, key=lambda x: x['ts'], reverse=True)

    # Add up to 4 most recent entries to recent_players
    for entry in merged[:4]:
        recent_players.append(entry)

    # Always show 5 (pad with empty if needed)
    while len(recent_players) < 5:
        recent_players.append({'name': '', 'status': 'empty', 'icon': '', 'amount': None, 'team': None})
    # --- CSS for panel ---
    st.markdown('''
    <style>
    .recent-panel-row {
        display: flex;
        flex-direction: row;
        gap: 12px;
        margin-bottom: 18px;
        margin-top: 6px;
        justify-content: flex-start;
        flex-wrap: wrap;
    }
    .recent-card {
        min-width: 70px;
        max-width: 240px;
        min-height: 54px;
        background: #e3f0ff;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(26,115,232,0.07);
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        justify-content: center;
        padding: 8px 14px 8px 12px;
        font-family: inherit;
        position: relative;
        border: 2px solid #b6d6ff;
        transition: all 0.2s ease;
        flex-grow: 1;
    }
    .recent-card.sold {
        background: #eafff2;
        border-color: #b6f5d8;
    }
    .recent-card.unsold {
        background: #fff0f0;
        border-color: #ffb6b6;
    }
    .recent-card.bidding {
        background: #fffbe6;
        border-color: #ffe066;
    }
    .recent-card .recent-title {
        font-size: clamp(14px, 2vw, 15px);
        font-weight: 700;
        color: #222;
        margin-bottom: 2px;
        display: flex;
        align-items: center;
        gap: 6px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        width: 100%;
    }
    .recent-card .recent-status {
        font-size: clamp(13px, 2vw, 14px);
        font-weight: 800;
        margin-top: 1px;
        letter-spacing: 0.2px;
        display: flex;
        align-items: center;
        width: 100%;
    }
    .recent-card.sold .recent-status {
        color: #28a745;
    }
    .recent-card.unsold .recent-status {
        color: #dc3545;
    }
    .recent-card.bidding .recent-status {
        color: #e67e22;
    }
    .recent-card .recent-team {
        font-size: clamp(12px, 2vw, 13px);
        color: #1a73e8;
        font-weight: 600;
        margin-left: 8px;
    }
    
    /* Responsive adjustments */
    @media (max-width: 1200px) {
        .recent-panel-row {
            gap: 10px;
        }
        .recent-card {
            min-width: 160px;
            padding: 6px 12px 6px 10px;
        }
    }
    
    @media (max-width: 992px) {
        .recent-panel-row {
            gap: 8px;
            margin-bottom: 14px;
        }
        .recent-card {
            min-width: 140px;
            min-height: 50px;
        }
    }
    
    @media (max-width: 768px) {
        .recent-panel-row {
            gap: 6px;
            margin-bottom: 12px;
        }
        .recent-card {
            min-width: 120px;
            min-height: 46px;
            padding: 5px 10px 5px 8px;
        }
        .recent-card .recent-title {
            font-size: 13px;
            gap: 4px;
        }
        .recent-card .recent-status {
            font-size: 12px;
        }
    }
    
    @media (max-width: 576px) {
        .recent-panel-row {
            gap: 4px;
        }
        .recent-card {
            min-width: calc(50% - 8px);
            min-height: 42px;
        }
    }
    
    /* Hover effects */
    .recent-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(26,115,232,0.12);
    }
    .recent-card.sold:hover {
        box-shadow: 0 4px 12px rgba(40,167,69,0.12);
    }
    .recent-card.unsold:hover {
        box-shadow: 0 4px 12px rgba(220,53,69,0.12);
    }
    .recent-card.bidding:hover {
        box-shadow: 0 4px 12px rgba(230,126,34,0.12);
    }
    </style>
''', unsafe_allow_html=True)


    # Bidding section
    active_item = get_active_item()
    recent_status = None # 'sold' or 'unsold' or None

    if not active_item:
        # Check for recently unsold (within 4 seconds)
        current_ts = datetime.now().timestamp()
        c.execute("SELECT id, name, rating, category, nationality, image_url, base_price, current_bid, is_active, winner_team, unsold_timestamp FROM items WHERE is_active = 0 AND unsold_timestamp > ? LIMIT 1", (current_ts - 4,))
        recent_unsold = c.fetchone()
        
        if recent_unsold:
            active_item = recent_unsold + (None,0.0) # Add dummy previous_team and timestamp to match tuple size
            recent_status = 'unsold'
        else:
             # Check for recently sold (within 4 seconds)
            c.execute("SELECT item_name, timestamp, team_bought, sold_amount FROM sold_items ORDER BY id DESC LIMIT 1")
            last_sold = c.fetchone()
            if last_sold:
                name, ts_str, winner, amount = last_sold
                try:
                    ts = datetime.fromisoformat(ts_str).timestamp()
                    if current_ts - ts < 4:
                        c.execute("SELECT id, name, rating, category, nationality, image_url, base_price, current_bid, is_active, winner_team, unsold_timestamp, previous_team, last_activity_timestamp FROM items WHERE name = ?", (name,))
                        item_details = c.fetchone()
                        if item_details:
                            active_item = item_details
                            recent_status = 'sold'
                except Exception as e:
                    pass

    if not active_item:
        # No item is currently open for bidding, show an image
        c.execute("SELECT logo_url FROM sponsors WHERE name = 'No Bidding Placeholder'")
        no_bidding_img = c.fetchone()
        img_url = no_bidding_img[0] if no_bidding_img else "https://i.postimg.cc/rm46tZSY/Untitled-design-(2).gif"
        st.image(img_url, use_container_width=True)
    else:
        item_id, item_name, item_rating, item_category, item_nationality, item_image_url, item_base_price, current_bid, is_active, winner, unsold_timestamp, previous_team, last_activity_ts = active_item
        
        # Auto-refresh for Timer
        if is_active == 1:
             # st_autorefresh(interval=1000, limit=None, key="bidding_timer_refresh")
             
             # Timer Logic
             # Timer Logic
             bid_duration = 60 # Default fallback
             try:
                 c.execute("SELECT value FROM global_settings WHERE key = 'timing_bid_duration'")
                 row_bd = c.fetchone()
                 if row_bd:
                     bid_duration = int(row_bd[0])
             except: pass
             
             elapsed = datetime.now().timestamp() - (last_activity_ts if last_activity_ts else datetime.now().timestamp())
             time_left = max(0, bid_duration - elapsed)
             
             # Sync debug variables for layout usage later
             debug_bid_duration = bid_duration
             debug_time_left = time_left
             
             # Progress Bar color logic
             progress_val = time_left / bid_duration
             timer_color = "green"
             if progress_val < 0.5: timer_color = "orange"
             if progress_val < 0.2: timer_color = "red"
             
             # REMOVED: Old large timer display (Moved directly to Place Bid button)
             # st.markdown(f"""
             #    <div style="border: 2px solid {timer_color}; border-radius: 10px; padding: 10px; text-align: center; margin-bottom: 10px; background-color: rgba(0,0,0,0.1);">
             #        <h2 style="color: {timer_color}; margin:0;">⏱️ {int(time_left)}s</h2>
             #    </div>
             #    <style>
             #        div.stProgress > div > div > div > div {{
             #            background-color: {timer_color};
             #        }}
             #    </style>
             # """, unsafe_allow_html=True)
             st.progress(progress_val)
             
             # EXPIRED LOGIC
             if time_left <= 0:
                 # Check if RTM is already active to avoid infinite loop
                 if st.session_state.get('rtm_state', {}).get('active'):
                     pass  # Do nothing, let the UI handle RTM
                 # Check if any bids placed
                 # Use get_highest_bid() to check active bids table, as 'winner' field in items is only set on finalization.
                 elif get_highest_bid(item_id):
                      # Bids exist -> Stop Bidding
                      if attempt_stop_bidding(item_id):
                          st.rerun()
                 else:
                      # No bids -> Unsold
                      mark_as_unsold(item_id)
                      st.rerun()

        
        # Display the player's name at the top
        st.header(f"🟢 {item_name}")

        # Create three columns for image, current highest bid, and current bidder
        cols = st.columns([1, 1, 1, 1])  # Equal width columns with no gap

        # Player Image Section
        with cols[0]:
            st.markdown(
                f"""
                <div style="
                    width: 100%;
                    padding: 15px;
                    border: 1px solid rgba(255, 255, 255, 0.6);
                    border-radius: 16px;
                    background: linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%);
                    text-align: center;
                    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
                    margin: 0;
                    height: 280px;
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    align-items: center;
                    position: relative;
                    overflow: hidden;
                    font-family: 'Inter', sans-serif;
                ">
                    <div class="image-container" style="
                        width: 200px;
                        height: 220px;
                        overflow: hidden;
                        border-radius: 16px;
                        position: relative;
                        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                    ">
                        <img src="{item_image_url}" 
                            style="
                                width: 100%;
                                height: 100%;
                                object-fit: cover;
                                transition: transform 0.5s cubic-bezier(0.4, 0, 0.2, 1);
                                border-radius: 16px;
                            "
                        />
                        <div style="
                            position: absolute;
                            bottom: 0;
                            left: 0;
                            right: 0;
                            padding: 0;
                            background: linear-gradient(to top, 
                                rgba(0,0,0,0.9) 0%,
                                rgba(0,0,0,0.7) 50%,
                                transparent 100%);
                            transition: all 0.3s ease;
                        ">
                            <p style="
                                margin: 0;
                                color: white;
                                font-weight: 600;
                                font-size: 20px;
                                text-shadow: 0 2px 4px rgba(0,0,0,0.3);
                                transform: translateY(0);
                                transition: transform 0.3s ease;
                            ">{item_name}</p>
                        </div>
                    </div>
                </div>
                <style>
                    .image-container:hover {{
                        transform: translateY(-5px);
                        box-shadow: 
                            0 20px 25px rgba(0, 0, 0, 0.15),
                            0 10px 10px rgba(0, 0, 0, 0.08);
                    }}
                    .image-container:hover img {{
                        transform: scale(1.05);
                    }}
                    .image-container:hover p {{
                        transform: translateY(-5px);
                    }}
                </style>
                """,
                unsafe_allow_html=True
            )

        # Get the current bid from the database
        current_bid = active_item[7]  # current_bid field
        highest = get_highest_bid(item_id)
        current_team = highest[0] if highest else "No bids yet"

        # Current Highest Bid Section
        with cols[1]:
            current_bid_display = format_amount(current_bid)
            st.markdown(
                f"""
                <div style="
                    width: 100%;
                    padding: 10px;
                    border: 1px solid rgba(26, 115, 232, 0.2);
                    border-radius: 16px;
                    background: linear-gradient(145deg, #f0f8ff, #e0f7fa);
                    text-align: center;
                    box-shadow: 0 4px 6px rgba(26, 115, 232, 0.1);
                    height: 280px;
                    display: flex;
                    flex-direction: column;
                    justify-content: space-between;
                    position: relative;
                    overflow: hidden;
                ">
                    <div class="current-bid-header">
                        <h4 style="
                            margin: 0;
                            font-size: 22px;
                            font-weight: 700;
                            color: #1a73e8;
                        ">{'Current Bid' if highest else 'Base Price'}</h4>
                    </div>
                    <div class="current-bid-amount">
                        <span style="white-space: nowrap;">{current_bid_display}</span>
                    </div>
                    <div class="current-bid-details">
                        <div class="current-bid-detail">
                            <span class="current-bid-label">Rating</span>
                            <span class="current-bid-value">{item_rating}/100</span>
                        </div>
                        <div class="current-bid-detail">
                            <span class="current-bid-label">Specialization</span>
                            <span class="current-bid-value">{item_category}</span>
                        </div>
                        <div class="current-bid-detail">
                            <span class="current-bid-label">Nationality</span>
                            <span class="current-bid-value">{item_nationality}</span>
                        </div>
                    </div>
                </div>
                <style>
                    .current-bid-container {{
                        width: 100%;
                        padding: 15px;
                        border: 1px solid rgba(255, 255, 255, 0.6);
                        border-radius: 16px;
                        background: linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%);
                        text-align: center;
                        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
                        height: 280px;
                        display: flex;
                        flex-direction: column;
                        justify-content: space-between;
                        position: relative;
                        overflow: hidden;
                        font-family: 'Inter', sans-serif;
                    }}

                    .current-bid-header {{
                        background: linear-gradient(to right, #e3f2fd, #bbdefb);
                        padding: 8px;
                        border-radius: 12px;
                        height: 40px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        color: #1565c0;
                    }}

                    .current-bid-amount {{
                        font-size: 32px;
                        font-weight: 800;
                        color: #0d6efd;
                        background: white;
                        padding: 10px;
                        border-radius: 12px;
                        box-shadow: 0 4px 10px rgba(13, 110, 253, 0.1);
                        border: 1px solid #e7f1ff;
                        height: 70px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        margin: 10px 0;
                    }}

                    .current-bid-details {{
                        display: flex;
                        flex-direction: column;
                        gap: 8px;
                    }}

                    .current-bid-detail {{
                        padding: 8px 12px;
                        background: white;
                        border-radius: 8px;
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        border: 1px solid #f1f5f9;
                        font-size: 14px;
                    }}

                    .current-bid-label {{
                        font-weight: 600;
                        color: #64748b;
                    }}

                    .current-bid-value {{
                        color: #1e293b;
                        font-weight: 600;
                    }}
                </style>
                """,
                unsafe_allow_html=True
            )

        # Current Bidder Section
        with cols[2]:
            if recent_status == 'unsold':
                st.markdown(
                    f"""
                    <div style="
                        width: 100%;
                        padding: 20px;
                        border: 1px solid rgba(220,53,69,0.1);
                        border-radius: 24px;
                        background: linear-gradient(145deg, #fff5f5, #ffe6e6);
                        text-align: center;
                        box-shadow: 
                            0 4px 6px rgba(220, 53, 69, 0.02),
                            0 10px 15px rgba(220, 53, 69, 0.03),
                            0 20px 30px rgba(220, 53, 69, 0.04);
                        height: 280px;
                        display: flex;
                        flex-direction: column;
                        justify-content: center;
                        align-items: center;
                        position: relative;
                        overflow: hidden;
                        backdrop-filter: blur(10px);
                        -webkit-backdrop-filter: blur(10px);
                    ">
                        <div style="
                            width: 140px;
                            height: 140px;
                            background: white;
                            border-radius: 70px;
                            padding: 20px;
                            box-shadow: 
                                0 10px 20px rgba(220, 53, 69, 0.1),
                                0 6px 6px rgba(220, 53, 69, 0.06);
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            margin: 10px 0;
                            position: relative;
                        ">
                            <div style="
                                position: absolute;
                                inset: 10px;
                                border-radius: 50%;
                                border: 2px solid rgba(220,53,69,0.2);
                                animation: pulse 2s ease-in-out infinite;
                            "></div>
                            <span style="
                                font-size: 50px;
                                transform: scale(0.5);
                                transition: transform 0.3s ease;
                            ">❌</span>
                        </div>
                        <p style="
                            margin: 20px 0 0 0;
                            font-weight: 700;
                            background: linear-gradient(135deg, #dc3545, #c82333);
                            -webkit-background-clip: text;
                            -webkit-text-fill-color: transparent;
                            font-size: 24px;
                            font-family: system-ui, -apple-system, sans-serif;
                            letter-spacing: 1px;
                        ">UNSOLD</p>
                    </div>
                    <style>
                        @keyframes float {{
                            0%, 100% {{ transform: translateY(0); }}
                            50% {{ transform: translateY(-10px); }}
                        }}
                        @keyframes pulse {{
                            0% {{ transform: scale(1); opacity: 1; }}
                            50% {{ transform: scale(1.05); opacity: 0.5; }}
                            100% {{ transform: scale(1); opacity: 1; }}
                        }}
                    </style>
                    """,
                    unsafe_allow_html=True
                )
            elif recent_status == 'sold':
                # Get winner info
                winner_team_name = active_item[9] # winner_team
                c.execute("SELECT logo_url FROM teams WHERE name = ?", (winner_team_name,))
                res = c.fetchone()
                winner_logo = res[0] if res else ""
                
                st.markdown(
                    f"""
                    <div style="
                        width: 100%;
                        padding: 20px;
                        border: 1px solid rgba(40,167,69,0.1);
                        border-radius: 24px;
                        background: linear-gradient(145deg, #f0fff4, #dcfce7);
                        text-align: center;
                        box-shadow: 
                            0 4px 6px rgba(40, 167, 69, 0.02),
                            0 10px 15px rgba(40, 167, 69, 0.03),
                            0 20px 30px rgba(40, 167, 69, 0.04);
                        height: 280px;
                        display: flex;
                        flex-direction: column;
                        justify-content: center;
                        align-items: center;
                        position: relative;
                        overflow: hidden;
                        backdrop-filter: blur(10px);
                    ">
                        <div style="
                            width: 140px;
                            height: 140px;
                            background: white;
                            border-radius: 70px;
                            padding: 20px;
                            box-shadow: 
                                0 10px 20px rgba(40, 167, 69, 0.1),
                                0 6px 6px rgba(40, 167, 69, 0.06);
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            margin: 10px 0;
                            position: relative;
                            animation: bounce 2s infinite;
                        ">
                            <img src="{winner_logo}" style="width: 100%; height: 100%; object-fit: contain;">
                        </div>
                        <p style="
                            margin: 10px 0 0 0;
                            font-weight: 700;
                            background: linear-gradient(135deg, #28a745, #15803d);
                            -webkit-background-clip: text;
                            -webkit-text-fill-color: transparent;
                            font-size: 24px;
                            font-family: system-ui, -apple-system, sans-serif;
                            letter-spacing: 1px;
                        ">SOLD TO {winner_team_name}</p>
                    </div>
                    <style>
                        @keyframes bounce {{
                            0%, 100% {{ transform: translateY(0); }}
                            50% {{ transform: translateY(-10px); }}
                        }}
                    </style>
                    """,
                    unsafe_allow_html=True
                )
            elif current_team == "No bids yet":
                st.markdown(
                    f"""
                    <div style="
                        width: 100%;
                        padding: 10px;
                        border: 1px solid rgba(108,117,125,0.1);
                        border-radius: 16px;
                        background: linear-gradient(145deg, #f8f9fa, #e9ecef);
                        text-align: center;
                        box-shadow: 0 4px 6px rgba(108, 117, 125, 0.1);
                        height: 280px;
                        display: flex;
                        flex-direction: column;
                        justify-content: center;
                        align-items: center;
                        position: relative;
                        overflow: hidden;
                    ">
                        <div class="waiting-circle" style="
                            width: 140px;
                            height: 140px;
                            background: white;
                            border-radius: 70px;
                            padding: 20px;
                            box-shadow: 0 4px 8px rgba(108, 117, 125, 0.1);
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            position: relative;
                            margin: 10px 0;
                        ">
                            <div class="pulse-ring" style="
                                position: absolute;
                                inset: 5px;
                                border-radius: 50%;
                                border: 3px solid rgba(108,117,125,0.2);
                                animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
                            "></div>
                            <div class="pulse-ring" style="
                                position: absolute;
                                inset: 10px;
                                border-radius: 50%;
                                border: 3px solid rgba(108,117,125,0.15);
                                animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite 0.5s;
                            "></div>
                            <span style="
                                font-size: 50px;
                                color: #6c757d;
                                position: relative;
                                z-index: 1;
                                animation: bounce 2s ease infinite;
                            ">🤝</span>
                        </div>
                        <div style="
                            margin-top: 20px;
                            background: white;
                            padding: 12px;
                            border-radius: 16px;
                            box-shadow: 0 4px 8px rgba(108,117,125,0.1);
                            width: 80%;
                        ">
                            <p style="
                                margin: 0;
                                font-weight: 600;
                                background: linear-gradient(135deg, #6c757d, #495057);
                                -webkit-background-clip: text;
                                -webkit-text-fill-color: transparent;
                                font-size: 18px;
                                font-family: system-ui, -apple-system, sans-serif;
                                letter-spacing: 0.5px;
                                line-height: 1.2;
                                padding: 2px 10px;
                            ">Waiting for Bids</p>
                        </div>
                    </div>
                    <style>
                        @keyframes pulse {{
                            0% {{ transform: scale(1); opacity: 1; }}
                            50% {{ transform: scale(1.1); opacity: 0.5; }}
                            100% {{ transform: scale(1); opacity: 1; }}
                        }}
                        @keyframes bounce {{
                            0%, 100% {{ transform: translateY(0); }}
                            50% {{ transform: translateY(-10px); }}
                        }}
                        .waiting-circle:hover {{
                            transform: scale(1.05);
                            transition: transform 0.3s ease;
                        }}
                        .waiting-circle:hover .pulse-ring {{
                            animation-duration: 1.5s;
                        }}
                    </style>
                    """,
                    unsafe_allow_html=True
                )
            else:
                c.execute("SELECT logo_url FROM teams WHERE name = ?", (current_team,))
                team_logo_result = c.fetchone()
                team_logo_url = team_logo_result[0] if team_logo_result else ""
                
                st.markdown(
                    f"""
                    <div style="
                        width: 100%;
                        padding: 15px;
                        border: 1px solid rgba(255, 255, 255, 0.6);
                        border-radius: 16px;
                        background: linear-gradient(135deg, #ffffff 0%, #f0fdf4 100%);
                        text-align: center;
                        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
                        height: 280px;
                        display: flex;
                        flex-direction: column;
                        justify-content: center;
                        align-items: center;
                        position: relative;
                        overflow: hidden;
                        font-family: 'Inter', sans-serif;
                    ">
                        <div class="bidder-circle" style="
                            width: 140px;
                            height: 140px;
                            background: white;
                            border-radius: 70px;
                            padding: 20px;
                            box-shadow: 0 4px 8px rgba(40, 167, 69, 0.1);
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            position: relative;
                            margin: 10px 0;
                            transition: transform 0.3s ease;
                        ">
                            <div class="paddle-effect" style="
                                position: absolute;
                                inset: 5px;
                                border-radius: 50%;
                                border: 3px solid rgba(40,167,69,0.3);
                                animation: paddle 1.5s ease-in-out infinite;
                            "></div>
                            <img src="{team_logo_url}" 
                                class="team-logo"
                                style="
                                    max-width: 100%;
                                    max-height: 100%;
                                    object-fit: contain;
                                    transition: transform 0.3s ease;
                                "
                            />
                        </div>
                        <div style="
                            margin-top: 20px;
                            background: white;
                            padding: 8px 20px;
                            border-radius: 10px;
                            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                            border: 1px solid #e2e8f0;
                            min-width: 60%;
                        ">
                            <div style="
                                font-weight: 700;
                                color: #1e293b;
                                font-size: 18px;
                                letter-spacing: 0.5px;
                            ">{current_team}</div>
                        </div>
                    </div>
                    <style>
                        @keyframes paddle {{
                            0% {{ transform: scale(1) rotate(0deg); }}
                            25% {{ transform: scale(1.1) rotate(90deg); }}
                            50% {{ transform: scale(1) rotate(180deg); }}
                            75% {{ transform: scale(1.1) rotate(270deg); }}
                            100% {{ transform: scale(1) rotate(360deg); }}
                        }}
                        .bidder-circle:hover {{
                            transform: scale(1.05);
                        }}
                        .bidder-circle:hover .team-logo {{
                            transform: scale(1.1);
                        }}
                        .bidder-circle:hover .paddle-effect {{
                            animation-duration: 1s;
                            border-width: 4px;
                        }}
                    </style>
                    """,
                    unsafe_allow_html=True
                )

        # Initialize a session state variable to track the number of bids placed
        if 'bid_count' not in st.session_state:
            st.session_state['bid_count'] = 0

        # Recent Bids and Status Section (Column 4)
        with cols[3]:
            # First part - Recent Bids
            st.markdown(
                f"""
                <div style="
                    width: 100%;
                    border: 1px solid rgba(255, 255, 255, 0.6);
                    border-radius: 16px;
                    background: linear-gradient(to right, #ecfdf5, #d1fae5);
                    text-align: center;
                    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.05);
                    height: 40px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin-bottom: 15px;
                ">
                    <h4 style="
                        margin: 0;
                        font-size: 16px;
                        font-weight: 700;
                        color: #047857;
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                    ">Recent Sold</h4>
                </div>
                """, unsafe_allow_html=True)
            
            # Fetch recent bids for this item
            c.execute("SELECT team_name, amount, timestamp FROM bids WHERE item_id = ? ORDER BY timestamp DESC LIMIT 3", (item_id,))
            recent_bids = c.fetchall()

            # Fetch and display the four most recent sold items
            c.execute("SELECT item_name, team_bought, sold_amount FROM sold_items ORDER BY timestamp DESC LIMIT 2")
            recent_sold_items = c.fetchall()

            # Calculate how many items to show
            total_items = len(recent_bids) + len(recent_sold_items)
            
            # Determine how many recent bids and sold items to show
            bids_to_show = recent_bids[:max(0, 5 - len(recent_sold_items))]
            sold_to_show = recent_sold_items[:max(0, 5 - len(bids_to_show))]

            # Display recent bids
            for bid in bids_to_show:
                team, amount, timestamp = bid
                formatted_amount = format_amount(amount)
                st.markdown(
                    f"""
                    <div class="bid-card" style="
                        background: #fff;
                        padding: 11.5px;
                        border-radius: 10px;
                        border: 1px solid rgba(40, 167, 69, 0.2);
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        box-shadow: 0 2px 4px rgba(40, 167, 69, 0.1);
                        margin-bottom: 12px;
                    ">
                        <div style="
                            display: flex;
                            align-items: center;
                            gap: 10px;
                            font-weight: 600;
                            color: #1a73e8;
                        ">
                            {team}
                        </div>
                        <div style="
                            display: flex;
                            align-items: center;
                            gap: 10px;
                        ">
                            <span style="color: #28a745; font-weight: 600;">{formatted_amount}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            # Display recent sold items
            for item_name, team_bought, sold_amount in sold_to_show:
                # Truncate item name to a maximum of 12 characters, ensuring at least 10 characters are visible
                if len(item_name) > 12:
                    truncated_item_name = item_name[:12] + ' '
                else:
                    truncated_item_name = item_name  # Show the full name if it's 12 characters or less

                # Ensure the item name is displayed in a single line
                formatted_amount = format_amount(sold_amount) if sold_amount else ""  # Format the sold amount if available
                st.markdown(
                    f"""
                    <div style="
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        padding: 11px;
                        border: 1px solid rgba(40, 167, 69, 0.3);
                        border-radius: 12px;
                        background: linear-gradient(145deg, #e8f5e9, #f0fff4);
                        margin-bottom: 12px;
                        margin-top: 0;
                        white-space: nowrap;  /* Prevent line breaks */
                        overflow: hidden;     /* Hide overflow */
                        text-overflow: ellipsis; /* Add ellipsis for overflow */
                    ">
                        <div style="
                            font-size: 16px;
                            font-weight: 600;
                            color: #1a73e8;
                            flex-grow: 1;
                        ">{truncated_item_name}</div>
                        <div style="
                            display: flex;
                            align-items: center;
                            gap: 10px;
                            font-size: 16px;
                            font-weight: 600;
                            color: #28a745;
                            text-align: right;
                        ">
                            <span>{team_bought}</span>
                            <span>{formatted_amount}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            if not bids_to_show and not sold_to_show:
                st.markdown(
                    """
                    <div style="
                        padding: 10px;
                        color: #6c757d;
                        font-style: italic;
                    ">
                        No recent bids or sold items.
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    # Check if admin is authenticated
    if 'admin_authenticated' not in st.session_state or not st.session_state['admin_authenticated']:
        # Custom CSS for the Place Bid button
        st.markdown("""
            <style>
            div.stButton > button {
                background-color: #015f26 !important;
                color: white !important;
                border: none;
                border-radius: 5px;
                font-weight: bold;
                height: 46px; /* Match input height */
            }
            div.stButton > button:hover {
                background-color: #014f20 !important;
                color: white !important;
            }
            </style>
        """, unsafe_allow_html=True)

        # Add margin top
        st.markdown('<div style="margin-top: 40px;"></div>', unsafe_allow_html=True)
        
        # Display Refund Message if exists
        if 'refund_message' in st.session_state:
             msg = st.session_state.pop('refund_message')
             st.success(msg)
             st.toast(msg, icon="💰")

        # --- GLOBAL RTM STATE MANAGEMENT (Runs for Everyone) ---
        if active_item and not recent_status:
             rtm_state = st.session_state.get('rtm_state', {})
             rtm_active_global = rtm_state.get('active')
             rtm_item_id_global = rtm_state.get('item_id')

             # 1. Force Reset Check (Manual Reset)
             if 'force_rtm_reset' in st.session_state and st.session_state['force_rtm_reset']:
                  st.session_state['rtm_state'] = {'active': False, 'item_id': None, 'prev_team': None, 'bidder': None, 'amount': 0}
                  st.session_state['force_rtm_reset'] = False
                  st.rerun()
            
             # 2. ID Mismatch Check
             if rtm_active_global and rtm_item_id_global != item_id:
                  st.session_state['rtm_state'] = {'active': False, 'item_id': None, 'prev_team': None, 'bidder': None, 'amount': 0}
                  st.rerun()

             # 3. No Bids Check (Failsafe)
             if rtm_active_global and not get_highest_bid(item_id):
                  st.session_state['rtm_state'] = {'active': False, 'item_id': None, 'prev_team': None, 'bidder': None, 'amount': 0}
                  st.rerun()

             # 4. Timestamp Check (Global Sync Logic)
             # If the auction's last activity (Start/Restart) is NEWER than the local RTM trigger time, 
             # it means the auction was reset globally, so local RTM state is stale.
             rtm_ts = rtm_state.get('timestamp', 0)
             if rtm_active_global and last_activity_ts and rtm_ts < last_activity_ts:
                  st.session_state['rtm_state'] = {'active': False, 'item_id': None, 'prev_team': None, 'bidder': None, 'amount': 0}
                  st.rerun()
        # -------------------------------------------------------

        # ------------------------------------------------------------------
        # FLAT LAYOUT refactor for balanced button sizes
        # Determine layout based on RTM existence
        # Check if RTM exists for this player (needed for layout decision)
        has_rtm = False
        if active_item:
             # Tuple unpack: index 11 is previous_team
             # item_id, item_name, item_rating, item_category, item_nationality, item_image_url, item_base_price, current_bid, is_active, winner, unsold_timestamp, previous_team, last_activity_ts = active_item
             # But active_item is already unpacked way above? No, it's unpacked inside 'else' usually.
             # Wait, active_item IS unpacked at line 1839 (global scope).
             # Let's verify line 1839 context. It seems available. 
             # Let's just safely access it from the tuple since 'active_item' variable is available here.
             prev_team_val = active_item[11]
             has_rtm = prev_team_val and prev_team_val != "None"

             if has_rtm:
                 # Check Eligibility specific to this team and player (Limits Check)
                 try:
                     # active_item index 4 is nationality
                     # active_item is unpacked from get_active_item(). Tuple indices:
                     # 0:id, 1:name, 2:rating, 3:cat, 4:nationality ...
                     
                     p_nat_layout = active_item[4]
                     is_indian_layout = (p_nat_layout == 'India')
                     
                     if not check_rtm_eligibility(prev_team_val, is_indian_layout):
                         has_rtm = False # Hide it!
                 except Exception as e:
                     print(f"RTM Layout Check Error: {e}")
                     pass

        # Check global RTM setting from DB (Source of Truth for all users)
        rtm_enabled = True
        try:
            c.execute("SELECT value FROM global_settings WHERE key = 'rtm_option'")
            row_opt = c.fetchone()
            if row_opt:
                rtm_enabled = (row_opt[0] == 'true')
        except Exception:
            pass

        if has_rtm and rtm_enabled:
             # Layout: [Team] [Pass] [Timer] [RTM] [Bid] - All Equal Widths
             c_team, c_pass, c_timer, c_rtm, c_bid = st.columns([1, 1, 1, 1, 1], gap="small")
        else:
             # Layout: [Team] [Pass] [Timer] [Bid] - All Equal Widths
             c_team, c_pass, c_timer, c_bid = st.columns([1, 1, 1, 1], gap="small")
             c_rtm = None

        # 1. SELECT TEAM
        with c_team:
            # Check for existing session
            default_index = None
            if 'selected_team' in st.session_state and st.session_state['selected_team'] in team_names:
                default_index = team_names.index(st.session_state['selected_team'])

            # Show Select Team
            selected_team = st.selectbox("Select Team", team_names, label_visibility="collapsed", index=default_index, placeholder="Select Team")

        # Find the selected team's details
        selected_team_details = next((team for team in available_teams if team[0] == selected_team), None)

        password_verified = False
        team_name = None
        budget = 0

        # 2. PASSWORD INPUT
        if selected_team_details:
            if len(selected_team_details) == 3:
                team_name, budget, password = selected_team_details
                
                with c_pass:
                    # Password input field
                    default_password = ""
                    if 'team_password' in st.session_state and 'selected_team' in st.session_state:
                         if st.session_state['selected_team'] == team_name:
                             default_password = st.session_state['team_password']

                    password_input = st.text_input("Password", value=default_password, type="password", label_visibility="collapsed", placeholder="Password")

                # Check if the password is correct
                if password_input == password:
                    st.session_state['team_password'] = password
                    st.session_state['selected_team'] = team_name
                    password_verified = True

        # 3. BIDDING CONTROLS (Timer, RTM, Button)
        if active_item and not recent_status:
            # Inject CSS to force ALL buttons in this section to 40px height
            # Inject CSS to force ALL buttons in this section to 40px height + Premium Look 
            st.markdown("""
                <style>
                div.stButton > button {
                    height: 40px !important;
                    padding-top: 0px !important;
                    padding-bottom: 0px !important;
                    border-radius: 12px !important; /* Slightly more rounded */
                    font-weight: 600 !important;
                    box-shadow: 0 4px 6px rgba(50, 50, 93, 0.11), 0 1px 3px rgba(0, 0, 0, 0.08) !important;
                    transition: all 0.2s ease-in-out !important;
                    border: none !important;
                    background: linear-gradient(135deg, #ffffff 0%, #f7f9fc 100%) !important; /* Default Light Gradient */
                    color: #2c3e50 !important;
                }
                div.stButton > button:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 7px 14px rgba(50, 50, 93, 0.1), 0 3px 6px rgba(0, 0, 0, 0.08) !important;
                    background: linear-gradient(135deg, #fefefe 0%, #eef1f5 100%) !important;
                }
                
                /* Target Primary Buttons (Bid, Accept) for Green Gradient */
                div.stButton > button[kind="primary"] {
                    background: linear-gradient(135deg, #198754 0%, #157347 100%) !important;
                    color: white !important;
                }
                div.stButton > button[kind="primary"]:hover {
                    background: linear-gradient(135deg, #1a945d 0%, #146c43 100%) !important;
                }

                /* Input fields styling to match height/look approx */
                div[data-baseweb="select"] > div, 
                div[data-baseweb="input"] > div,
                div.stTextInput > div > div {
                    height: 40px !important;
                    border-radius: 12px !important;
                    background-color: #ffffff !important;
                    border: 1px solid #e2e8f0 !important;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.02) !important;
                }
                
                /* Aggressively target the actual input element */
                input[type="password"], input[type="text"] {
                     background-color: #ffffff !important;
                     color: #333 !important;
                }
                
                /* Fix for Streamlit's specific input class */
                .stTextInput input {
                    background-color: #ffffff !important;
                }
                </style>
            """, unsafe_allow_html=True)

            # --- RTM STATE LOGIC ---
            rtm_state = st.session_state.get('rtm_state', {})
            rtm_active = rtm_state.get('active')
            rtm_item_id = rtm_state.get('item_id')

            # Self-healing logic
            if rtm_active and rtm_item_id != item_id:
                    st.session_state['rtm_state'] = {'active': False, 'item_id': None, 'prev_team': None, 'bidder': None, 'amount': 0}
                    rtm_active = False # Local update
                    st.rerun()

            if 'force_rtm_reset' in st.session_state and st.session_state['force_rtm_reset']:
                    st.session_state['rtm_state'] = {'active': False, 'item_id': None, 'prev_team': None, 'bidder': None, 'amount': 0}
                    st.session_state['force_rtm_reset'] = False
                    rtm_active = False # Local update
                    st.rerun()

            is_rtm_now = rtm_active and rtm_state.get('item_id') == item_id
            
            # Debug Info Calculation
            debug_bid_duration = 60
            try:
                c.execute("SELECT value FROM global_settings WHERE key = 'timing_bid_duration'")
                row_bd = c.fetchone()
                if row_bd:
                    debug_bid_duration = int(row_bd[0])
            except: pass
            
            debug_elapsed = datetime.now().timestamp() - (last_activity_ts if last_activity_ts else datetime.now().timestamp())
            debug_time_left = max(0, debug_bid_duration - debug_elapsed)
            
            if is_rtm_now:
                # --- RTM DECISION PHASE ---
                
                rtm = rtm_state
                prev_team_clean = rtm['prev_team'].strip().lower() if rtm['prev_team'] else ""
                
                user_is_holder = False
                if password_verified and team_name:
                    current_team_clean = team_name.strip().lower()
                    if current_team_clean == prev_team_clean:
                        user_is_holder = True
                
                # RTM Phase Timer (Still useful)
                with c_timer:
                     st.markdown(f"""
                        <div style="
                            text-align: center; font-size: 16px; font-weight: 700; 
                            color: #dc3545; background: #fff; 
                            border: 2px solid #dc3545; border-radius: 10px; 
                            padding: 0px; height: 40px; width: 100%; 
                            display: flex; align-items: center; justify-content: center;
                            box-shadow: 0 2px 5px rgba(0,0,0,0.08); font-family: 'Inter', sans-serif;
                        ">
                            <span style="margin-right:4px;">⏱️</span> RTM
                        </div>
                        """, unsafe_allow_html=True)
                
                # Re-use RTM/Bid columns for decision
                if user_is_holder:
                    if c_rtm:
                         with c_rtm:
                            # Enforce RTM Limits
                            rtm_stats = get_rtm_stats(team_name)
                            
                            # Get Limits from DB
                            limits = get_rtm_limits()
                            limit_total = limits['total']
                            limit_indian = limits['indian']
                            limit_overseas = limits['overseas']

                            # Check Nationality of current player
                            # active_item: index 4 is nationality
                            p_nat = active_item[4]
                            is_indian = (p_nat == 'India')

                            # Check Validity
                            can_rtm = True
                            err_msg = ""

                            if rtm_stats['total'] >= limit_total:
                                can_rtm = False
                                err_msg = "Total RTM Limit Reached!"
                            elif is_indian and rtm_stats['indian'] >= limit_indian:
                                can_rtm = False
                                err_msg = "Indian RTM Limit Reached!"
                            elif not is_indian and rtm_stats['overseas'] >= limit_overseas:
                                can_rtm = False
                                err_msg = "Overseas RTM Limit Reached!"

                            if can_rtm:
                                if st.button("✅ Accept", use_container_width=True, type="primary"):
                                    team_budget_val = get_team_budget(team_name)
                                    if team_budget_val >= rtm['amount']:
                                        finalize_item_sale(recipient_team=team_name, is_rtm=True)
                                        st.session_state['rtm_state']['active'] = False
                                        st.success(f"Sold via RTM!")
                                        st.rerun()
                                    else:
                                        st.error("Budget!")
                            else:
                                st.error(err_msg)
                                st.button("🚫 RTM Locked", disabled=True, use_container_width=True)
                    
                    with c_bid:
                        if st.button("❌ Decline", use_container_width=True):
                            finalize_item_sale()
                            st.session_state['rtm_state']['active'] = False
                            st.info("Declined.")
                            st.rerun()
                else:
                    # Viewer or Non-Holder Team
                    # Replace st.info with custom div for perfect alignment
                    with c_bid:
                        st.markdown(f"""
                        <div style="
                            text-align: center; font-size: 14px; font-weight: 600;
                            color: #0c5460;
                            background-color: #d1ecf1;
                            border-radius: 10px; 
                            height: 40px; width: 100%; 
                            display: flex; align-items: center; justify-content: center; 
                            border: 1px solid #bee5eb;
                            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
                        ">
                            Waiting for {rtm['prev_team']}...
                        </div>
                        """, unsafe_allow_html=True)
                        
            else:
                # --- STANDARD BIDDING ---
                
                # TIMER
                with c_timer:
                    pct = debug_time_left / debug_bid_duration
                    t_color = "#28a745" # Green
                    if pct < 0.5: t_color = "#ffc107" # Orange
                    if pct < 0.2: t_color = "#dc3545" # Red
                    
                    st.markdown(f"""
                    <div style="
                        text-align: center; font-size: 18px; font-weight: 800; 
                        color: {t_color}; background: #fff;
                        border: 2px solid {t_color}; border-radius: 10px; 
                        height: 40px; width: 100%; 
                        display: flex; align-items: center; justify-content: center;
                        box-shadow: 0 2px 5px rgba(0,0,0,0.08); font-family: 'Inter', sans-serif;
                    ">
                        {int(debug_time_left)}s
                    </div>
                    """, unsafe_allow_html=True)

                # RTM BADGE
                if has_rtm and c_rtm:
                    with c_rtm:
                         st.markdown(f"""
                        <div style="
                            text-align: center; font-size: 14px; font-weight: 700; 
                            color: #155724; background-color: #d4edda; 
                            border-color: #c3e6cb; border-radius: 10px; 
                            height: 40px; width: 100%; 
                            display: flex; flex-direction: column; align-items: center; justify-content: center; 
                            border: 1px solid #c3e6cb;
                            box-shadow: 0 2px 5px rgba(0,0,0,0.05); line-height: 1.1;
                        ">
                            <span style="font-size: 9px; color: #666; text-transform:uppercase; letter-spacing:0.5px;">RTM With</span>
                            <span style="font-size: 13px;">{prev_team_val}</span>
                        </div>
                        """, unsafe_allow_html=True)
                
                # BID BUTTON
                with c_bid:
                    if password_verified and team_name:
                        if st.button("🔨 Place Bid", use_container_width=True):
                            if budget < current_bid + BID_INCREMENT:
                                st.warning(f"Low Budget!")
                            else:
                                place_bid(item_id, team_name, current_bid)
                                st.session_state['selected_team'] = team_name
                                st.rerun()
                    else:
                        st.markdown(f"""
                        <div style="
                            text-align: center; font-size: 14px; font-weight: 600;
                            color: #6c757d; background: #e9ecef; 
                            border-radius: 10px; height: 40px; width: 100%; 
                            display: flex; align-items: center; justify-content: center; 
                            border: 1px solid #ced4da;
                            box-shadow: inset 0 1px 2px rgba(0,0,0,0.05);
                        ">
                            Login to Bid
                        </div>
                        """, unsafe_allow_html=True)





    # Sponsors Section
    # Sponsors Section
    c.execute("SELECT name, logo_url FROM sponsors WHERE name NOT IN ('No Bidding Placeholder', 'Title Sponsor')")
    sponsors_data = c.fetchall()
    sponsors = [{"name": s[0], "logo": s[1]} for s in sponsors_data]

    sponsor_html = """
    <style>
    .sponsor-grid {
        display: flex;
        flex-wrap: wrap;
        gap: 15px;
        justify-content: center;
        margin-top: 20px;
        padding: 5px;
    }
    .sponsor-card {
        background: #ffffff;
        border-radius: 16px;
        padding: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05), 0 1px 3px rgba(0,0,0,0.02);
        width: 110px;
        height: 90px;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        border: 1px solid rgba(241, 245, 249, 1);
        filter: grayscale(10%);
    }
    .sponsor-card:hover {
        transform: translateY(-4px) scale(1.02);
        box-shadow: 0 12px 20px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.05);
        border-color: #cbd5e1;
        filter: grayscale(0%);
    }
    .sponsor-img {
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
        transition: transform 0.3s ease;
    }
    </style>
    <div class="sponsor-grid">
    """
    
    for sponsor in sponsors:
        sponsor_html += f'<div class="sponsor-card" title="{sponsor["name"]}"><img class="sponsor-img" src="{sponsor["logo"]}" alt="{sponsor["name"]}"></div>'
    sponsor_html += '</div>'

    st.markdown(sponsor_html, unsafe_allow_html=True)

# Tab 2: Players Market
with tab2:
    st.subheader("Players Market")
    
    # Add dropdown to select which table to view
    market_view = st.selectbox(
        "Select View",
        ["Players Sold", "Players Unsold"],
        key="market_view"
    )
    
    # Show the selected table based on dropdown choice
    if market_view == "Players Sold":
        # Update the SQL query to change the order of columns
        # Update the SQL query to change the order of columns AND fetch is_rtm
        c.execute("SELECT item_name, rating, category, nationality, sold_amount, team_bought, is_rtm FROM sold_items ORDER BY timestamp DESC")
        sold_items = c.fetchall()

        if sold_items:
            st.markdown("""
                <style>
                    .sold-table {
                        margin-top: 20px;
                        border-radius: 10px;
                        overflow: hidden;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                    }
                </style>
            """, unsafe_allow_html=True)
            
            # Check global RTM setting for suffix
            rtm_enabled_market = True
            try:
                c.execute("SELECT value FROM global_settings WHERE key = 'rtm_option'")
                row_opt_mk = c.fetchone()
                if row_opt_mk:
                    rtm_enabled_market = (row_opt_mk[0] == 'true')
            except: pass

            # Convert the sold amounts to the formatted version
            formatted_sold_items = []
            for item in sold_items:
                # item tuple: (name, rating, cat, nat, amount, team, is_rtm)
                name = item[0]
                is_rtm = item[6]
                
                # Append R symbol if RTM and Enabled
                display_name = f"{name} (R)" if is_rtm and rtm_enabled_market else name
                
                formatted_item = list(item[:6]) # Access first 6 items
                formatted_item[0] = display_name
                formatted_item[4] = format_amount(item[4])  # Format the sold_amount
                formatted_sold_items.append(formatted_item)
            
            sold_df = pd.DataFrame(
                formatted_sold_items,
                columns=["Player Name", "Rating", "Specialization", "Nationality", "Sold Amount", "Team Bought"]
            )
            st.dataframe(
                sold_df,
                use_container_width=True,
                height=400,
                hide_index=True
            )
        else:
            st.info("No players have been sold yet.")
    
    else:  # Players Unsold view
        # Update the query to include base_price
        c.execute("""
            SELECT i.name AS item_name, i.rating, i.category, i.nationality, i.base_price, 'Unsold' AS status 
            FROM items i 
            WHERE i.is_active = 0 AND i.winner_team = 'UNSOLD'
            ORDER BY i.unsold_timestamp DESC
        """)
        unsold_items = c.fetchall()

        if unsold_items:
            st.markdown("""
                <style>
                    .unsold-table {
                        margin-top: 20px;
                        border-radius: 10px;
                        overflow: hidden;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                    }
                </style>
            """, unsafe_allow_html=True)
            
            # Update the DataFrame to include the base price
            formatted_unsold_items = []
            for item in unsold_items:
                formatted_item = list(item)
                formatted_item[4] = format_amount(item[4])  # Format the base_price
                formatted_unsold_items.append(formatted_item)
            
            unsold_df = pd.DataFrame(
                formatted_unsold_items,
                columns=["Player Name", "Rating", "Specialization", "Nationality", "Base Price", "Status"]
            )
            st.dataframe(
                unsold_df,
                use_container_width=True,
                height=400,
                hide_index=True
            )
        else:
            st.info("No players are currently unsold.")

# Tab 3: Team Squad
with tab3:
    st.subheader("Team Squad")
    
    # Dropdown for team selection
    selected_team_name = st.selectbox("Select Team", team_names, key="squad_team_select")

    # After the team selection, display the squad information
    if selected_team_name:
        team_info = get_team_squad_info(selected_team_name)

        # Create columns for the information display
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"Total Spend Amount: {format_amount(team_info['total_spent'])}")
            st.write(f"Total Rating: {team_info['total_rating']}")
            st.write(f"Remaining Budget: {format_amount(team_info['remaining_budget'])}")
            st.write(f"Total Players Bought: {team_info['total_players_bought']}")
            
            # Check global RTM setting
            rtm_enabled_squad = True
            try:
                c.execute("SELECT value FROM global_settings WHERE key = 'rtm_option'")
                row_opt_squad = c.fetchone()
                if row_opt_squad:
                    rtm_enabled_squad = (row_opt_squad[0] == 'true')
            except: pass

            if rtm_enabled_squad:
                # RTM Stats (Indian & Overseas only)
                rtm_stats_squad = get_rtm_stats(selected_team_name)
                rtm_limits_squad = get_rtm_limits()
                
                rem_indian = rtm_limits_squad['indian'] - rtm_stats_squad['indian']
                rem_overseas = rtm_limits_squad['overseas'] - rtm_stats_squad['overseas']
                
                st.write(f"Indian RTM: {rem_indian} / {rtm_limits_squad['indian']}")
                st.write(f"Overseas RTM: {rem_overseas} / {rtm_limits_squad['overseas']}")
        
        with col2:
            st.write(f"Batters: {team_info['num_batters']}")
            st.write(f"Bowlers: {team_info['num_bowlers']}")
            st.write(f"Allrounders: {team_info['num_allrounders']}")
            st.write(f"Wicketkeepers: {team_info['num_wicketkeepers']}")
            st.write(f"Indian Players: {team_info['num_indian_players']}")
            st.write(f"Foreign Players: {team_info['num_foreign_players']}")

        # Fetch and display the squad in a table
        # Fetch and display the squad in a table with RTM status
        # Join with sold_items to check is_rtm status
        # Fetch and display the squad in a table with RTM status and Amount
        # Join with sold_items to check is_rtm status and fetch sold_amount
        c.execute("""
            SELECT i.name, i.rating, i.category, i.nationality, s.sold_amount, s.is_rtm 
            FROM items i 
            LEFT JOIN sold_items s ON i.name = s.item_name 
            WHERE i.winner_team = ?
        """, (selected_team_name,))
        players = c.fetchall()

        if players:
            # Process data to add (R) and Amount
            formatted_players = []
            for p in players:
                name, rating, cat, nat, amount, is_rtm = p
                # rtm_enabled_squad already fetched above in the same scope
                display_name = f"{name} (R)" if is_rtm and rtm_enabled_squad else name
                
                fmt_amount = format_amount(amount) if amount is not None else "0"
                
                # Order: Name, Rating, Specialization, Sold Price, Nationality
                formatted_players.append([display_name, rating, cat, fmt_amount, nat])
                
            players_df = pd.DataFrame(formatted_players, columns=["Player Name", "Rating", "Specialization", "Sold Price", "Nationality"])
            st.dataframe(players_df, use_container_width=True, hide_index=True)
        else:
            st.write("No players found for this team.")
    else:
        st.warning("Please select a team to view the squad information.")

# Tab 4: Auction History
with tab4:
    st.subheader("Auction History")
    
    # Fetch sold items ordered by timestamp in descending order
    c.execute("SELECT item_name, team_bought, is_rtm FROM sold_items ORDER BY timestamp DESC")
    sold_items = c.fetchall()

    # Fetch unsold items ordered by timestamp in descending order
    c.execute("SELECT item_name FROM unsold_items ORDER BY timestamp DESC")
    unsold_items = c.fetchall()

    # Display sold items
    # Check global RTM setting for suffix
    rtm_enabled_hist = True
    try:
        c.execute("SELECT value FROM global_settings WHERE key = 'rtm_option'")
        row_opt_hist = c.fetchone()
        if row_opt_hist:
            rtm_enabled_hist = (row_opt_hist[0] == 'true')
    except: pass

    for item in sold_items:
        name = item[0]
        team = item[1]
        is_rtm = item[2]
        
        display_name = f"{name} (R)" if is_rtm and rtm_enabled_hist else name
        st.write(f"✅ **{display_name}** SOLD TO **{team}**")

    # Display unsold items
    for item in unsold_items:
        st.write(f"❌ **{item[0]}** UNSOLD (No Team is interested)")

# Tab 5: Special Bidding Zone
with tab5:
    st.subheader("Special Bidding Zone")
    
    # Fetch the current active item
    active_item = get_active_item()
    
    if active_item:
        item_id, item_name, item_rating, item_category, item_nationality, item_image_url, item_base_price, current_bid, is_active, winner, unsold_timestamp, previous_team, last_activity_ts = active_item
        
        # Get current bid from database
        current_bid_amount = current_bid
        
        # Fetch the highest bid for the current item
        highest_bid = get_highest_bid(item_id)
        
        if highest_bid:
            current_bidder = highest_bid[0]
        else:
            current_bidder = "No bids yet"
            
        # Time Left Calculation for Special Zone
        bid_duration_special = 60
        try:
             c.execute("SELECT value FROM global_settings WHERE key = 'timing_bid_duration'")
             row_bd = c.fetchone()
             if row_bd:
                 bid_duration_special = int(row_bd[0])
        except: pass
        
        elapsed_special = datetime.now().timestamp() - (last_activity_ts if last_activity_ts else datetime.now().timestamp())
        time_left_special = max(0, bid_duration_special - elapsed_special)
        
        # Color coding for timer
        timer_color_bg = "#d4edda" # Greenish
        timer_color_text = "#155724"
        if time_left_special < 20:
            timer_color_bg = "#fff3cd" # Yellowish
            timer_color_text = "#856404"
        if time_left_special < 10:
            timer_color_bg = "#f8d7da" # Reddish
            timer_color_text = "#721c24"
        
        # Display the item details with premium responsive card
        # Display the item details with premium responsive card
        st.markdown(
            f"""
<style>
.special-card-container {{ background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%); border-radius: 20px; padding: 25px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); border: 1px solid rgba(255,255,255,0.8); margin-bottom: 20px; font-family: 'Inter', sans-serif; }}
.special-card-content {{ display: flex; flex-direction: row; align-items: center; gap: 30px; }}
.special-img-wrapper {{ flex-shrink: 0; position: relative; }}
.special-run-img {{ width: 140px; height: 140px; border-radius: 50%; object-fit: cover; border: 4px solid #ffffff; box-shadow: 0 8px 20px rgba(0,0,0,0.15); transition: transform 0.3s ease; }}
.special-run-img:hover {{ transform: scale(1.05); }}
.special-info {{ flex-grow: 1; }}
.special-name {{ font-size: 28px; font-weight: 800; background: linear-gradient(90deg, #1a1a1a 0%, #4a4a4a 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin: 0 0 10px 0; text-transform: uppercase; letter-spacing: -0.5px; }}
.special-stat-row {{ display: flex; align-items: center; gap: 15px; margin-bottom: 8px; }}
.special-badge {{ background: #e3f2fd; color: #0d47a1; padding: 4px 12px; border-radius: 20px; font-size: 13px; font-weight: 600; border: 1px solid #bbdefb; }}
.timer-badge {{ background: {timer_color_bg}; color: {timer_color_text}; padding: 4px 12px; border-radius: 20px; font-size: 14px; font-weight: 700; border: 1px solid rgba(0,0,0,0.1); display: inline-flex; align-items: center; gap: 5px; }}
.special-price-box {{ background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 12px 20px; border-radius: 12px; display: inline-block; margin-top: 15px; box-shadow: 0 4px 15px rgba(40, 167, 69, 0.3); }}
.special-price-label {{ font-size: 12px; opacity: 0.9; text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }}
.special-price-val {{ font-size: 24px; font-weight: 700; }}
@media (max-width: 600px) {{
    .special-card-content {{ flex-direction: column; text-align: center; gap: 20px; }}
    .special-stat-row {{ justify-content: center; }}
    .special-run-img {{ width: 120px; height: 120px; }}
    .special-name {{ font-size: 24px; }}
    .special-price-box {{ width: 100%; text-align: center; }}
}}
</style>
<div class="special-card-container">
<div class="special-card-content">
<div class="special-img-wrapper"><img src="{item_image_url}" class="special-run-img"/></div>
<div class="special-info">
<h2 class="special-name">{item_name}</h2>
<div class="special-stat-row"><span style="color: #666; font-size: 14px;">Current Bidder:</span><span class="special-badge">{current_bidder}</span></div>
<div class="special-stat-row"><span style="color: #666; font-size: 14px;">Time Left:</span><span class="timer-badge">⏱️ {int(time_left_special)}s</span></div>
<div class="special-price-box"><div class="special-price-label">Current Bid</div><div class="special-price-val">{format_amount(current_bid_amount)}</div></div>
</div>
</div>
</div>
""",
            unsafe_allow_html=True
        )
        
        # Check if the user has selected a team and entered the password
        if 'selected_team' in st.session_state and 'team_password' in st.session_state:
            if st.button("    💰                      Bid", key="big_bid"):
                # Logic to place a big bid
                place_bid(item_id, st.session_state['selected_team'], current_bid_amount)
                st.toast("Bid Placed Successfully! 🚀", icon="✅")
                time.sleep(0.1) 
                st.rerun()
        else:
            st.warning("Please select a team and enter the password in the Bidding & Budgets tab to enable bidding.")
    else:
        st.warning("No item is currently available for bidding.")
