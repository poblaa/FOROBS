"""
Electronic Logbook with Data Calculator for Ship Engineers
Main application - Logbook page
"""

import streamlit as st
import pandas as pd
import altair as alt
import sqlite3
from datetime import datetime
import os
import json
import time
import sys
import socket
import subprocess

# Database setup
DB_PATH = "logbook.db"
ELCALC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'elcalc')
ELCALC_PORT = 8502

# M/E Cylinder oil specific consumption constant [g/kWh]
ME_CYL_OIL_G_PER_KWH = 0.0007

def _is_local_port_open(port, host='127.0.0.1', timeout=0.2):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((host, int(port))) == 0
    except Exception:
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass

def _ensure_elcalc_server():
    """Ensure local static server for elcalc is running; return (ok, url)."""
    _url = f"http://127.0.0.1:{ELCALC_PORT}/index.html"
    if not os.path.isdir(ELCALC_DIR):
        return False, _url
    if _is_local_port_open(ELCALC_PORT):
        return True, _url
    try:
        _popen_kwargs = {
            'cwd': ELCALC_DIR,
            'stdout': subprocess.DEVNULL,
            'stderr': subprocess.DEVNULL,
        }
        if os.name == 'nt' and hasattr(subprocess, 'CREATE_NO_WINDOW'):
            _popen_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        subprocess.Popen(
            [sys.executable, '-m', 'http.server', str(ELCALC_PORT), '--bind', '127.0.0.1'],
            **_popen_kwargs,
        )
        time.sleep(0.4)
        return _is_local_port_open(ELCALC_PORT), _url
    except Exception:
        return False, _url

# Card dimension settings (editable in card_settings.json)
_CARD_SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'card_settings.json')
def _load_card_settings():
    try:
        with open(_CARD_SETTINGS_PATH, 'r') as f:
            return json.load(f)
    except Exception:
        return {}
CARD_S = _load_card_settings()
_inp_s = CARD_S.get('input_card', {})
_eco_s = CARD_S.get('event_card_output', {})
_eci_s = CARD_S.get('event_card_input', {})

# App settings (user-configurable via Settings panel)
_APP_SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app_settings.json')

def _load_app_settings():
    """Load user app settings from JSON file."""
    defaults = {
        'dep_stops_me_counters': 'no',
        'boiler_fuel_mode': 'flowmeter',
        'boiler_user_defined_rate': 0.0,
    }
    try:
        if os.path.exists(_APP_SETTINGS_PATH):
            with open(_APP_SETTINGS_PATH, 'r') as _f:
                data = json.load(_f)
                defaults.update(data)
    except (json.JSONDecodeError, OSError):
        pass
    return defaults

def _save_app_settings(settings):
    """Save user app settings to JSON file. Returns True on success, False on error."""
    try:
        with open(_APP_SETTINGS_PATH, 'w') as _f:
            json.dump(settings, _f, indent=4)
        return True
    except OSError:
        return False

def init_db():
    """Initialize SQLite database with events table"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            time TEXT,
            event TEXT,
            place TEXT,
            me_rev_c REAL,
            main_flmtr REAL,
            dg_in_flmtr REAL,
            dg_out_flmtr REAL,
            blr_flmtr REAL,
            cyl_oil_count REAL,
            me_pwrmtr REAL,
            me_hrs REAL,
            dg1_hrs REAL,
            dg2_hrs REAL,
            dg3_hrs REAL,
            boiler_hrs REAL,
            dg1_mwh REAL,
            dg2_mwh REAL,
            dg3_mwh REAL,
            sox_co2 REAL,
            ocl_pp_a REAL,
            ocl_pp_b REAL,
            ocl_pp_c REAL,
            phe_a REAL,
            phe_b REAL,
            sea_temp REAL,
            st_lo_tmp REAL,
            wcu_sep REAL,
            comp_1 REAL,
            comp_2 REAL,
            w_comp REAL
        )
    ''')
    conn.commit()

    # ---- Add new calculated / ROB / consumption columns if missing ----
    _new_columns = [
        # Calculated time/diff fields (stored as TEXT HH:MM)
        ('st_time', 'TEXT'),
        ('me_diff', 'TEXT'),
        ('dg1_diff', 'TEXT'),
        ('dg2_diff', 'TEXT'),
        ('dg3_diff', 'TEXT'),
        ('blr_diff', 'TEXT'),
        # ME performance
        ('avg_pwr', 'REAL'),
        ('avg_rpm', 'REAL'),
        ('ttl_pwr', 'REAL'),
        # Oil ROBs
        ('me_sys_rob', 'REAL'),
        ('me_cyl_rob', 'REAL'),
        ('dg_sys_rob', 'REAL'),
        # Oil CALC consumption
        ('me_sys_calc_cons', 'REAL'),   # user input from oil card
        ('me_cyl_calc_cons', 'REAL'),   # auto: avg_pwr * 0.0007 * st_time_h
        ('dg_sys_calc_cons', 'REAL'),   # user input from oil card
        # Oil COR consumption (user correction from oil card)
        ('me_sys_cor_cons', 'REAL'),
        ('me_cyl_cor_cons', 'REAL'),
        ('dg_sys_cor_cons', 'REAL'),
        # Oil ACC consumption (accepted = COR if >0, else CALC)
        ('me_sys_acc_cons', 'REAL'),
        ('me_cyl_acc_cons', 'REAL'),
        ('dg_sys_acc_cons', 'REAL'),
        # Fuel ROBs
        ('hfo_rob', 'REAL'),
        ('do_rob', 'REAL'),
        # Fuel type settings (HFO or DO)
        ('me_fo_set', 'TEXT'),
        ('dg_fo_set', 'TEXT'),
        ('blr_fo_set', 'TEXT'),
        # Fuel CALC consumption
        ('me_hfo_calc_cons', 'REAL'),
        ('me_do_calc_cons', 'REAL'),
        ('dg_hfo_calc_cons', 'REAL'),
        ('dg_do_calc_cons', 'REAL'),
        ('blr_hfo_calc_cons', 'REAL'),
        ('blr_do_calc_cons', 'REAL'),
        # Fuel COR consumption (user correction)
        ('me_hfo_cor_cons', 'REAL'),
        ('me_do_cor_cons', 'REAL'),
        ('dg_hfo_cor_cons', 'REAL'),
        ('dg_do_cor_cons', 'REAL'),
        ('blr_hfo_cor_cons', 'REAL'),
        ('blr_do_cor_cons', 'REAL'),
        # Fuel ACC consumption (accepted = COR if >0, else CALC)
        ('me_hfo_acc_cons', 'REAL'),
        ('me_do_acc_cons', 'REAL'),
        ('dg_hfo_acc_cons', 'REAL'),
        ('dg_do_acc_cons', 'REAL'),
        ('blr_hfo_acc_cons', 'REAL'),
        ('blr_do_acc_cons', 'REAL'),
        # Bunkering
        ('hfo_bnkr', 'REAL'),
        ('do_bnkr', 'REAL'),
        ('me_sys_bnkr', 'REAL'),
        ('me_cyl_bnkr', 'REAL'),
        ('dg_sys_bnkr', 'REAL'),
        # TTL RPM (total revolution diff)
        ('ttl_rpm', 'REAL'),
    ]
    existing = {row[1] for row in c.execute("PRAGMA table_info(events)").fetchall()}
    for col_name, col_type in _new_columns:
        if col_name not in existing:
            c.execute(f"ALTER TABLE events ADD COLUMN {col_name} {col_type}")
    conn.commit()
    conn.close()


def ensure_seed_event():
    """Ensure Event ID 1 (seed) exists with baseline values to avoid division by zero.
    If ID 1 exists but is not the seed, shift all events up by 1 to make room."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, place FROM events WHERE id = 1")
    row = c.fetchone()
    if row is not None and row[1] == 'SEED':
        conn.close()
        return  # Seed already in place
    if row is not None:
        # Shift all existing events up by 1 to make room for seed at ID 1
        max_id = c.execute("SELECT MAX(id) FROM events").fetchone()[0] or 0
        for old_id in range(max_id, 0, -1):
            c.execute("UPDATE events SET id = ? WHERE id = ?", (old_id + 1, old_id))
        conn.commit()
    seed = {
        'date': '28-01-26', 'time': '01:10', 'event': 'NOON', 'place': 'SEED',
        'me_rev_c': 1, 'main_flmtr': 1, 'dg_in_flmtr': 1, 'dg_out_flmtr': 1,
        'blr_flmtr': 1, 'cyl_oil_count': 1, 'me_pwrmtr': 1,
        'me_hrs': 1.00, 'dg1_hrs': 1.00, 'dg2_hrs': 1.00, 'dg3_hrs': 1.00,
        'boiler_hrs': 1.00, 'dg1_mwh': 1.00, 'dg2_mwh': 1.00, 'dg3_mwh': 1.00,
        'sox_co2': 1.00,
        'ocl_pp_a': 1.00, 'ocl_pp_b': 1.00, 'ocl_pp_c': 1.00,
        'phe_a': 1.00, 'phe_b': 1.00,
        'sea_temp': 1.0, 'st_lo_tmp': 1.0,
        'wcu_sep': 1.00, 'comp_1': 1.00, 'comp_2': 1.00, 'w_comp': 1.00,
        # Seed ROBs and settings
        'me_sys_rob': 1.00, 'me_cyl_rob': 1.00, 'dg_sys_rob': 1.00,
        'hfo_rob': 1.00, 'do_rob': 1.00,
        'me_fo_set': 'HFO', 'dg_fo_set': 'HFO', 'blr_fo_set': 'HFO',
        # Seed diffs / calc values
        'st_time': '00:00', 'me_diff': '00:00', 'dg1_diff': '00:00',
        'dg2_diff': '00:00', 'dg3_diff': '00:00', 'blr_diff': '00:00',
        'avg_pwr': 0, 'avg_rpm': 0, 'ttl_pwr': 0, 'ttl_rpm': 0,
        # Bunkering defaults
        'hfo_bnkr': 0, 'do_bnkr': 0,
        'me_sys_bnkr': 0, 'me_cyl_bnkr': 0, 'dg_sys_bnkr': 0,
    }
    cols = ', '.join(seed.keys())
    placeholders = ', '.join(['?' for _ in seed])
    c.execute(f"INSERT INTO events (id, {cols}) VALUES (1, {placeholders})", list(seed.values()))
    conn.commit()
    conn.close()


def get_connection():
    """Get database connection"""
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def _get_events_cache_nonce():
    try:
        if '_events_cache_nonce' not in st.session_state:
            st.session_state['_events_cache_nonce'] = 0
        return int(st.session_state['_events_cache_nonce'])
    except Exception:
        return 0


def invalidate_events_cache():
    try:
        st.session_state['_events_cache_nonce'] = _get_events_cache_nonce() + 1
        st.session_state.pop('_events_df_cache', None)
    except Exception:
        pass
    try:
        _fetch_all_events_cached.clear()
    except Exception:
        pass


@st.cache_data(show_spinner=False)
def _fetch_all_events_cached(_nonce: int):
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM events ORDER BY id DESC", conn)
    conn.close()
    return df


def fetch_all_events():
    """Fetch all events from database"""
    return _fetch_all_events_cached(_get_events_cache_nonce())


def fetch_all_events_stable():
    """Fetch events with retry and fallback cache to avoid transient empty sidebar table."""
    try:
        df = fetch_all_events()
    except Exception:
        df = pd.DataFrame()

    if not df.empty:
        st.session_state['_events_df_cache'] = df.copy()
        return df

    cached = st.session_state.get('_events_df_cache')
    if isinstance(cached, pd.DataFrame) and not cached.empty:
        return cached.copy()

    return df


def _normalize_numeric_payload(data: dict) -> dict:
    """Normalize numeric payload values before DB write (max 2 decimals)."""
    int_keys = {'me_rev_c', 'cyl_oil_count'}
    normalized = {}
    for key, value in data.items():
        if isinstance(value, bool):
            normalized[key] = value
        elif isinstance(value, int):
            normalized[key] = int(value)
        elif isinstance(value, float):
            normalized[key] = int(round(value)) if key in int_keys else round(float(value), 2)
        else:
            normalized[key] = value
    return normalized


def insert_event(data: dict):
    """Insert new event into database"""
    data = _normalize_numeric_payload(data)
    conn = get_connection()
    c = conn.cursor()
    columns = ', '.join(data.keys())
    placeholders = ', '.join(['?' for _ in data])
    c.execute(f"INSERT INTO events ({columns}) VALUES ({placeholders})", list(data.values()))
    conn.commit()
    conn.close()
    invalidate_events_cache()


def update_event(event_id: int, data: dict):
    """Update existing event"""
    data = _normalize_numeric_payload(data)
    conn = get_connection()
    c = conn.cursor()
    set_clause = ', '.join([f"{k} = ?" for k in data.keys()])
    values = list(data.values()) + [event_id]
    c.execute(f"UPDATE events SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    invalidate_events_cache()


def delete_event(event_id: int):
    """Delete event from database and renumber IDs to keep continuity"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    c.execute("SELECT id FROM events ORDER BY id ASC")
    rows = c.fetchall()
    for new_id, (old_id,) in enumerate(rows, start=1):
        if old_id != new_id:
            c.execute("UPDATE events SET id = ? WHERE id = ?", (new_id, old_id))
    conn.commit()
    conn.close()
    invalidate_events_cache()


# ============ CALCULATION ENGINE ============

def _g(row, key, fallback=0.0):
    """Safe get numeric value from a row dict"""
    v = row.get(key)
    if v is None or v == '' or v == 'None':
        return fallback
    try:
        return float(v)
    except (ValueError, TypeError):
        return fallback


def _parse_event_datetime(row):
    """Parse event date+time into datetime object"""
    from datetime import datetime as _dt
    date_str = str(row.get('date', '') or '')
    time_str = str(row.get('time', '') or '00:00')
    try:
        d = _dt.strptime(date_str, '%d-%m-%y')
    except ValueError:
        d = _dt(2026, 1, 28)
    try:
        parts = time_str.split(':')
        d = d.replace(hour=int(parts[0]), minute=int(parts[1]) if len(parts) > 1 else 0)
    except (ValueError, IndexError):
        pass
    return d


def _minutes_to_hhmm(total_minutes):
    """Convert total minutes to HH:MM string"""
    if total_minutes < 0:
        total_minutes = 0
    h = int(total_minutes) // 60
    m = int(total_minutes) % 60
    return f"{h:02d}:{m:02d}"


def _hhmm_to_minutes(hhmm_str):
    """Convert HH:MM string to total minutes"""
    if not hhmm_str or hhmm_str == '':
        return 0
    try:
        parts = str(hhmm_str).split(':')
        return int(parts[0]) * 60 + (int(parts[1]) if len(parts) > 1 else 0)
    except (ValueError, IndexError):
        return 0


def _decimal_diff_to_hhmm(present_dec, previous_dec):
    """Calculate difference of decimal hours and return HH:MM string.
    Running hours are stored in decimal format (e.g. 91.90 = 91h 54m).
    Diff: present - previous, then convert decimal hours to HH:MM."""
    diff = present_dec - previous_dec
    if diff < 0:
        diff = 0
    hours = int(diff)
    frac = diff - hours
    minutes = round(frac * 60)
    if minutes >= 60:
        hours += 1
        minutes -= 60
    return f"{hours:02d}:{minutes:02d}"


def _decimal_diff_to_decimal_hours(present_dec, previous_dec):
    """Return difference in decimal hours (for division)."""
    diff = present_dec - previous_dec
    return max(diff, 0.0)


def _compute_calculated_values(present, previous):
    """Compute all derived fields for one event from present and previous row dicts."""
    calc = {}

    dt_present = _parse_event_datetime(present)
    dt_previous = _parse_event_datetime(previous)
    delta_minutes = max(0, int((dt_present - dt_previous).total_seconds() / 60))
    calc['st_time'] = _minutes_to_hhmm(delta_minutes)

    for col, diff_key in [('me_hrs', 'me_diff'), ('dg1_hrs', 'dg1_diff'),
                          ('dg2_hrs', 'dg2_diff'), ('dg3_hrs', 'dg3_diff'),
                          ('boiler_hrs', 'blr_diff')]:
        calc[diff_key] = _decimal_diff_to_hhmm(_g(present, col), _g(previous, col))

    me_diff_dec = _decimal_diff_to_decimal_hours(_g(present, 'me_hrs'), _g(previous, 'me_hrs'))
    ttl_pwr = _g(present, 'me_pwrmtr') - _g(previous, 'me_pwrmtr')
    calc['ttl_pwr'] = round(max(ttl_pwr, 0), 2)
    calc['avg_pwr'] = round(calc['ttl_pwr'] / me_diff_dec, 2) if me_diff_dec > 0 else 0.0

    rev_diff = _g(present, 'me_rev_c') - _g(previous, 'me_rev_c')
    me_diff_minutes = _hhmm_to_minutes(calc['me_diff'])
    calc['avg_rpm'] = round(max(rev_diff, 0) / me_diff_minutes, 2) if me_diff_minutes > 0 else 0.0
    calc['ttl_rpm'] = round(max(rev_diff, 0), 2)

    # M/E CYL oil consumption: avg_pwr [kW] * ME_CYL_OIL_G_PER_KWH [g/kWh] * st_time [h]
    calc['me_cyl_calc_cons'] = round(max(calc['avg_pwr'] * ME_CYL_OIL_G_PER_KWH * me_diff_dec, 0), 4)
    calc['me_sys_calc_cons'] = _g(present, 'me_sys_calc_cons')
    calc['dg_sys_calc_cons'] = _g(present, 'dg_sys_calc_cons')

    for prefix in ['me_sys', 'me_cyl', 'dg_sys']:
        cor = _g(present, f'{prefix}_cor_cons')
        cal = calc.get(f'{prefix}_calc_cons', _g(present, f'{prefix}_calc_cons'))
        calc[f'{prefix}_acc_cons'] = cor if cor > 0 else cal

    calc['me_sys_rob'] = round(_g(previous, 'me_sys_rob') - calc['me_sys_acc_cons'] + _g(present, 'me_sys_bnkr'), 2)
    calc['me_cyl_rob'] = round(_g(previous, 'me_cyl_rob') - calc['me_cyl_acc_cons'] + _g(present, 'me_cyl_bnkr'), 2)
    calc['dg_sys_rob'] = round(_g(previous, 'dg_sys_rob') - calc['dg_sys_acc_cons'] + _g(present, 'dg_sys_bnkr'), 2)

    for fs in ['me_fo_set', 'dg_fo_set', 'blr_fo_set']:
        val = present.get(fs)
        calc[fs] = (previous.get(fs) or 'HFO') if (not val or val == 'None') else val

    me_flmtr_diff = max(_g(present, 'main_flmtr') - _g(previous, 'main_flmtr'), 0)
    calc['me_hfo_calc_cons'] = round((me_flmtr_diff * 0.919) / 1000, 2) if calc['me_fo_set'] == 'HFO' else 0.0
    calc['me_do_calc_cons'] = round((me_flmtr_diff * 0.870) / 1000, 2) if calc['me_fo_set'] == 'DO' else 0.0

    blr_flmtr_diff = max(_g(present, 'blr_flmtr') - _g(previous, 'blr_flmtr'), 0)
    _blr_settings = _load_app_settings()
    _blr_mode = _blr_settings.get('boiler_fuel_mode', 'flowmeter')
    if _blr_mode == 'user_defined':
        _blr_user_rate = float(_blr_settings.get('boiler_user_defined_rate') or 0.0)
        _blr_hrs_diff = _decimal_diff_to_decimal_hours(_g(present, 'boiler_hrs'), _g(previous, 'boiler_hrs'))
        _blr_ud_cons = round(_blr_hrs_diff * _blr_user_rate, 4)
        calc['blr_hfo_calc_cons'] = _blr_ud_cons if calc['blr_fo_set'] == 'HFO' else 0.0
        calc['blr_do_calc_cons'] = _blr_ud_cons if calc['blr_fo_set'] == 'DO' else 0.0
    else:
        calc['blr_hfo_calc_cons'] = round((blr_flmtr_diff * 0.919) / 1000, 2) if calc['blr_fo_set'] == 'HFO' else 0.0
        calc['blr_do_calc_cons'] = round((blr_flmtr_diff * 0.870) / 1000, 2) if calc['blr_fo_set'] == 'DO' else 0.0

    dg_in_diff = _g(present, 'dg_in_flmtr') - _g(previous, 'dg_in_flmtr')
    dg_out_diff = _g(present, 'dg_out_flmtr') - _g(previous, 'dg_out_flmtr')
    dg_net_diff = max(dg_in_diff - dg_out_diff, 0)
    calc['dg_hfo_calc_cons'] = round((dg_net_diff * 0.919) / 1000, 2) if calc['dg_fo_set'] == 'HFO' else 0.0
    calc['dg_do_calc_cons'] = round((dg_net_diff * 0.870) / 1000, 2) if calc['dg_fo_set'] == 'DO' else 0.0

    # ── HFO / DO corrected consumption: proportional split among ALL devices ──
    # User enters total corrected HFO (me_hfo_cor_cons) and total corrected DO (me_do_cor_cons).
    # These are split proportionally among ME, DG, and BLR based on their calculated consumption,
    # but only for devices whose fuel setting matches that fuel type.

    me_hfo_cal  = calc['me_hfo_calc_cons']
    me_do_cal   = calc['me_do_calc_cons']
    dg_hfo_cal  = calc['dg_hfo_calc_cons']
    dg_do_cal   = calc['dg_do_calc_cons']
    blr_hfo_cal = calc['blr_hfo_calc_cons']
    blr_do_cal  = calc['blr_do_calc_cons']

    hfo_cor_total = _g(present, 'me_hfo_cor_cons')  # user input: total corrected HFO
    do_cor_total  = _g(present, 'me_do_cor_cons')    # user input: total corrected DO

    # HFO correction — split proportionally among all HFO consumers (ME, DG, BLR)
    if hfo_cor_total > 0:
        hfo_cal_sum = me_hfo_cal + dg_hfo_cal + blr_hfo_cal
        if hfo_cal_sum > 0:
            calc['me_hfo_acc_cons']  = round(hfo_cor_total * me_hfo_cal  / hfo_cal_sum, 2)
            calc['dg_hfo_acc_cons']  = round(hfo_cor_total * dg_hfo_cal  / hfo_cal_sum, 2)
            calc['blr_hfo_acc_cons'] = round(hfo_cor_total * blr_hfo_cal / hfo_cal_sum, 2)
        else:
            # No calculated HFO consumption — assign to first HFO device found
            calc['me_hfo_acc_cons']  = hfo_cor_total if calc['me_fo_set'] == 'HFO' else 0.0
            calc['dg_hfo_acc_cons']  = 0.0
            calc['blr_hfo_acc_cons'] = 0.0
            if calc['me_fo_set'] != 'HFO':
                if calc['dg_fo_set'] == 'HFO':
                    calc['dg_hfo_acc_cons'] = hfo_cor_total
                elif calc['blr_fo_set'] == 'HFO':
                    calc['blr_hfo_acc_cons'] = hfo_cor_total
    else:
        calc['me_hfo_acc_cons']  = me_hfo_cal
        calc['dg_hfo_acc_cons']  = dg_hfo_cal
        calc['blr_hfo_acc_cons'] = blr_hfo_cal

    # DO correction — split proportionally among all DO consumers (ME, DG, BLR)
    if do_cor_total > 0:
        do_cal_sum = me_do_cal + dg_do_cal + blr_do_cal
        if do_cal_sum > 0:
            calc['me_do_acc_cons']  = round(do_cor_total * me_do_cal  / do_cal_sum, 2)
            calc['dg_do_acc_cons']  = round(do_cor_total * dg_do_cal  / do_cal_sum, 2)
            calc['blr_do_acc_cons'] = round(do_cor_total * blr_do_cal / do_cal_sum, 2)
        else:
            # No calculated DO consumption — assign to first DO device found
            calc['me_do_acc_cons']  = 0.0
            calc['dg_do_acc_cons']  = 0.0
            calc['blr_do_acc_cons'] = 0.0
            if calc['me_fo_set'] == 'DO':
                calc['me_do_acc_cons'] = do_cor_total
            elif calc['dg_fo_set'] == 'DO':
                calc['dg_do_acc_cons'] = do_cor_total
            elif calc['blr_fo_set'] == 'DO':
                calc['blr_do_acc_cons'] = do_cor_total
            else:
                # No device explicitly set to DO — assign to DG as default DO consumer
                # (DGs are the typical DO consumers; mirrors how HFO defaults to ME)
                calc['dg_do_acc_cons'] = do_cor_total
    else:
        calc['me_do_acc_cons']  = me_do_cal
        calc['dg_do_acc_cons']  = dg_do_cal
        calc['blr_do_acc_cons'] = blr_do_cal

    # Store per-device corrected values for DB persistence
    calc['dg_hfo_cor_cons']  = calc['dg_hfo_acc_cons']  if hfo_cor_total > 0 else 0.0
    calc['dg_do_cor_cons']   = calc['dg_do_acc_cons']   if do_cor_total > 0 else 0.0
    calc['blr_hfo_cor_cons'] = calc['blr_hfo_acc_cons'] if hfo_cor_total > 0 else 0.0
    calc['blr_do_cor_cons']  = calc['blr_do_acc_cons']  if do_cor_total > 0 else 0.0

    calc['hfo_rob'] = round(
        _g(previous, 'hfo_rob')
        - calc['me_hfo_acc_cons']
        - calc['dg_hfo_acc_cons']
        - calc['blr_hfo_acc_cons']
        + _g(present, 'hfo_bnkr'), 2)
    calc['do_rob'] = round(
        _g(previous, 'do_rob')
        - calc['me_do_acc_cons']
        - calc['dg_do_acc_cons']
        - calc['blr_do_acc_cons']
        + _g(present, 'do_bnkr'), 2)

    return _normalize_numeric_payload(calc)


# ═══════════════════════════════════════════════════════
# ── CHART DATA — SFOC & DG CONSUMPTION PER HOUR ──────
# ═══════════════════════════════════════════════════════
CHART_DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chart_data.json')

def _hhmm_to_hours(v):
    """Convert HH:MM string to decimal hours."""
    if not v or v == 'None' or v == '00:00':
        return 0.0
    try:
        parts = str(v).split(':')
        return int(parts[0]) + int(parts[1]) / 60.0
    except (ValueError, IndexError):
        return 0.0


def _hhmm_to_minutes(v):
    """Convert HH:MM string to integer minutes."""
    if not v or v == 'None' or v == '00:00':
        return 0
    try:
        parts = str(v).split(':')
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return 0

def _compute_chart_point(ev):
    """Compute M/E SFOC and D/G cons/hr for one event row (dict)."""
    def _g(d, k):
        try:
            v = d.get(k)
            return float(v) if v is not None and str(v) != 'None' and v != '' else 0.0
        except (ValueError, TypeError):
            return 0.0

    eid = int(ev.get('id', 0))
    date_s = str(ev.get('date', ''))
    time_s = str(ev.get('time', ''))

    # M/E calculated SFOC: fuel [mT] / ttl_pwr [kWh] * 1_000_000 = g/kWh
    me_calc_hfo = _g(ev, 'me_hfo_acc_cons')
    me_calc_do  = _g(ev, 'me_do_acc_cons')
    me_calc_fuel = me_calc_hfo + me_calc_do  # total ME fuel in mT
    ttl_pwr = _g(ev, 'ttl_pwr')

    me_sfoc_calc = 0.0
    if ttl_pwr > 0 and me_calc_fuel > 0:
        me_sfoc_calc = round(me_calc_fuel / ttl_pwr * 1_000_000, 2)

    # M/E corrected SFOC
    me_cor_hfo = _g(ev, 'me_hfo_cor_cons')
    me_cor_do  = _g(ev, 'me_do_cor_cons')
    me_cor_fuel = me_cor_hfo + me_cor_do
    me_sfoc_cor = 0.0
    if ttl_pwr > 0 and me_cor_fuel > 0:
        me_sfoc_cor = round(me_cor_fuel / ttl_pwr * 1_000_000, 2)

    # D/G total running time (minutes)
    dg1_min = _hhmm_to_minutes(ev.get('dg1_diff'))
    dg2_min = _hhmm_to_minutes(ev.get('dg2_diff'))
    dg3_min = _hhmm_to_minutes(ev.get('dg3_diff'))
    dg_total_min = dg1_min + dg2_min + dg3_min

    # D/G calculated consumption [mT/h]
    dg_calc_hfo = _g(ev, 'dg_hfo_acc_cons')
    dg_calc_do  = _g(ev, 'dg_do_acc_cons')
    dg_calc_fuel = dg_calc_hfo + dg_calc_do
    dg_cons_calc = 0.0
    if dg_total_min > 0 and dg_calc_fuel > 0:
        dg_cons_calc = round((dg_calc_fuel / dg_total_min) * 60.0, 3)

    # D/G corrected consumption [mT/h]
    dg_cor_hfo = _g(ev, 'dg_hfo_cor_cons')
    dg_cor_do  = _g(ev, 'dg_do_cor_cons')
    dg_cor_fuel = dg_cor_hfo + dg_cor_do
    dg_cons_cor = 0.0
    if dg_total_min > 0 and dg_cor_fuel > 0:
        dg_cons_cor = round((dg_cor_fuel / dg_total_min) * 60.0, 3)

    return {
        'id': eid,
        'date': date_s,
        'time': time_s,
        'me_sfoc_calc': me_sfoc_calc,
        'me_sfoc_cor': me_sfoc_cor,
        'dg_cons_calc': dg_cons_calc,
        'dg_cons_cor': dg_cons_cor,
    }


def rebuild_chart_data():
    """Rebuild entire chart data JSON from database."""
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM events WHERE id > 1 ORDER BY id ASC").fetchall()
    except Exception:
        return
    finally:
        if conn:
            conn.close()

    points = []
    for row in rows:
        pt = _compute_chart_point(dict(row))
        points.append(pt)

    try:
        with open(CHART_DATA_PATH, 'w') as f:
            json.dump(points, f)
    except Exception:
        pass


def update_chart_point(event_id):
    """Update or insert one chart point for given event_id."""
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    except Exception:
        return
    finally:
        if conn:
            conn.close()

    if row is None:
        return

    pt = _compute_chart_point(dict(row))

    # Load existing data
    points = []
    try:
        if os.path.exists(CHART_DATA_PATH):
            with open(CHART_DATA_PATH, 'r') as f:
                points = json.load(f)
    except Exception:
        points = []

    # Find and replace or append
    replaced = False
    for i, p in enumerate(points):
        if p.get('id') == event_id:
            points[i] = pt
            replaced = True
            break
    if not replaced:
        points.append(pt)
        points.sort(key=lambda x: x.get('id', 0))

    try:
        with open(CHART_DATA_PATH, 'w') as f:
            json.dump(points, f)
    except Exception:
        pass


def load_chart_data():
    """Load chart data from JSON file."""
    try:
        if os.path.exists(CHART_DATA_PATH):
            with open(CHART_DATA_PATH, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return []

def calculate_event(event_id):
    """Calculate all derived values for one event and persist to DB."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row

    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if row is None:
        conn.close()
        return
    present = dict(row)

    prev_id = max(event_id - 1, 1)
    prev_row = conn.execute("SELECT * FROM events WHERE id = ?", (prev_id,)).fetchone()
    if prev_row is None:
        conn.close()
        return
    previous = dict(prev_row)

    calc = _compute_calculated_values(present, previous)
    set_clause = ', '.join([f"{k} = ?" for k in calc.keys()])
    values = list(calc.values()) + [event_id]
    conn.execute(f"UPDATE events SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    invalidate_events_cache()


def recalculate_chain(from_id):
    """Recalculate all events from from_id onward in a single batch transaction."""
    start_id = max(int(from_id) - 1, 1)
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM events WHERE id >= ? ORDER BY id ASC",
        (start_id,)
    ).fetchall()

    if len(rows) <= 1:
        conn.close()
        return

    updates = []
    previous = dict(rows[0])
    calc_keys = None

    for row in rows[1:]:
        present = dict(row)
        calc = _compute_calculated_values(present, previous)
        if calc_keys is None:
            calc_keys = list(calc.keys())
        updates.append([calc[k] for k in calc_keys] + [present['id']])
        previous = present.copy()
        previous.update(calc)

    if updates and calc_keys:
        set_clause = ', '.join([f"{k} = ?" for k in calc_keys])
        conn.executemany(f"UPDATE events SET {set_clause} WHERE id = ?", updates)
        conn.commit()

    conn.close()
    invalidate_events_cache()


def ensure_calculated_fields_ready_once():
    """Run one-time chain recalculation when transferred rows miss derived values."""
    if st.session_state.get('_calc_ready_checked', False):
        return
    st.session_state['_calc_ready_checked'] = True

    try:
        conn = get_connection()
        row_count = int(conn.execute("SELECT COUNT(*) FROM events WHERE id > 1").fetchone()[0] or 0)
        if row_count == 0:
            conn.close()
            return

        missing_count = int(conn.execute(
            """
            SELECT COUNT(*)
            FROM events
            WHERE id > 1
              AND (
                st_time IS NULL OR st_time = '' OR
                avg_pwr IS NULL OR avg_rpm IS NULL OR ttl_pwr IS NULL OR ttl_rpm IS NULL OR
                me_sys_rob IS NULL OR me_cyl_rob IS NULL OR dg_sys_rob IS NULL OR
                hfo_rob IS NULL OR do_rob IS NULL OR
                me_hfo_calc_cons IS NULL OR me_do_calc_cons IS NULL OR
                dg_hfo_calc_cons IS NULL OR dg_do_calc_cons IS NULL OR
                blr_hfo_calc_cons IS NULL OR blr_do_calc_cons IS NULL
              )
            """
        ).fetchone()[0] or 0)
        conn.close()

        if missing_count > 0:
            recalculate_chain(2)
    except Exception:
        pass


def decimal_to_hhmm(decimal_val):
    """Convert decimal hours to HH:MM format"""
    if decimal_val is None:
        return ""
    hours = int(decimal_val)
    minutes = int((decimal_val - hours) * 60)
    return f"{hours:02d}:{minutes:02d}"


def hhmm_to_decimal(hhmm_str):
    """Convert HH:MM to decimal hours"""
    if not hhmm_str or hhmm_str == "":
        return None
    try:
        parts = hhmm_str.split(":")
        hours = int(parts[0])
        minutes = int(parts[1]) if len(parts) > 1 else 0
        return hours + minutes / 60.0
    except:
        return None


# Helper: safe float parse
def _normalize_decimal_input(val):
    """Normalize user numeric input (accept both decimal dot and comma)."""
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        return s.replace(',', '.')
    return val


def safe_float(val, fallback=0.0):
    nval = _normalize_decimal_input(val)
    if nval is None:
        return fallback
    try:
        return round(float(nval), 2)
    except (ValueError, TypeError):
        return fallback

def safe_int(val, fallback=0):
    """Parse to integer, return fallback if empty/invalid"""
    nval = _normalize_decimal_input(val)
    if nval is None:
        return fallback
    try:
        return int(float(nval))
    except (ValueError, TypeError):
        return fallback

# Field type definitions
INTEGER_KEYS = {'me_rev_c', 'cyl_oil_count'}
HOURS_KEYS = {'me_hrs', 'dg1_hrs', 'dg2_hrs', 'dg3_hrs', 'boiler_hrs',
              'ocl_pp_a', 'ocl_pp_b', 'ocl_pp_c', 'phe_a', 'phe_b',
              'wcu_sep', 'comp_1', 'comp_2', 'w_comp'}
TEMP_KEYS = {'sea_temp', 'st_lo_tmp'}

def fmt_field(key, val):
    """Format field value for display in input card"""
    if val is None or val == '' or val == 0 or val == 0.0:
        return ""
    if key in INTEGER_KEYS:
        return str(int(float(val)))
    if key in HOURS_KEYS:
        return f"{float(val):.2f}"
    if key in TEMP_KEYS:
        return f"{float(val):.1f}"
    # Other numeric fields (me_pwrmtr, dg_mwh, sox_co2)
    v = float(val)
    return f"{v:.2f}" if v != int(v) else str(int(v))

VALID_MINUTES = {'00','06','12','18','24','30','36','42','48','54'}

# DEP lock: fields that must be copied from previous event when DEPARTURE is selected
_DEP_ME_FIELDS = ['me_rev_c', 'main_flmtr', 'cyl_oil_count', 'me_pwrmtr', 'me_hrs']

def _get_prev_event_for_dep(editing_id=None):
    """Return dict of previous event values for DEP M/E counter lock.
    If editing_id is given, get the event just before it; otherwise get the latest."""
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        if editing_id and int(editing_id) > 1:
            row = conn.execute(
                "SELECT * FROM events WHERE id < ? ORDER BY id DESC LIMIT 1",
                (int(editing_id),)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT 1"
            ).fetchone()
        conn.close()
        return dict(row) if row else {}
    except Exception:
        return {}

# ---- Card layout persistence ----
LAYOUT_FILE = "card_layout.json"
DEFAULT_LAYOUT = {
    "event_card_output": {"top": 17, "right": 500, "locked": False},
    "event_card_input": {"top": 17, "right": 950, "locked": False},
    "input_card": {"top": 20, "right": 19, "locked": False},
    "functions_panel": {"top": 650, "right": 19, "locked": False},
    "settings_panel": {"top": 640, "right": 230, "locked": False},
    "me_sfoc_chart": {"top": 440, "right": 500, "locked": False},
    "dg_chart": {"top": 440, "right": 950, "locked": False}
}

def load_card_layout():
    """Load saved card positions from JSON file"""
    try:
        with open(LAYOUT_FILE, 'r') as f:
            saved = json.load(f)
        for k in DEFAULT_LAYOUT:
            if k not in saved:
                saved[k] = DEFAULT_LAYOUT[k]
        return saved
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_LAYOUT.copy()

def save_card_layout(layout):
    """Save card positions to JSON file for cross-browser persistence"""
    with open(LAYOUT_FILE, 'w') as f:
        json.dump(layout, f, indent=2)

_card_layout = load_card_layout()

# Initialize database
init_db()
ensure_seed_event()

# Page config - sidebar for logbook
st.set_page_config(
    page_title="Ship Logbook",
    page_icon="\U0001F6A2",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    /* Hide Streamlit elements */
    #MainMenu {display: none !important;}
    footer {display: none !important;}
    header[data-testid="stHeader"] {display: none !important; height: 0 !important;}
    header {display: none !important; height: 0 !important;}
    
    /* Main container - push content to the right */
    .block-container {
        padding: 0rem 1rem 0.5rem 1rem;
        max-width: 100%;
    }
    section[data-testid="stMain"] > div:first-child {
        padding-top: 0 !important;
    }
    
    .stApp {
        background-color: #f5f5f5;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    
    /* ===== LEFT BAR (Sidebar) - OVERLAY MODE ===== */
    [data-testid="stSidebar"] {
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        height: 100vh !important;
        z-index: 999 !important;
        background-color: #ffffff;
        border-right: none !important;
        box-shadow: 4px 0 15px rgba(0,0,0,0.2);
        overflow-y: auto !important;
        transition: none !important;
    }
    /* Prevent main content from being pushed by sidebar */
    [data-testid="stAppViewBlockContainer"],
    .main .block-container {
        margin-left: 0 !important;
        max-width: 100% !important;
    }
    .stApp > div:first-child {
        margin-left: 0 !important;
    }
    section[data-testid="stMain"] {
        margin-left: 0 !important;
        width: 100% !important;
    }
    [data-testid="stSidebar"] > div:first-child { padding-top: 0rem; }
    /* Hide ALL sidebar collapse/close/resize controls */
    [data-testid="collapsedControl"],
    [data-testid="stSidebarCollapseButton"],
    [data-testid="stSidebar"] button[kind="header"],
    [data-testid="stSidebar"] button[aria-label="Close"],
    [data-testid="stSidebar"] [data-testid="stSidebarNavCollapseButton"],
    button[aria-expanded][data-testid="stSidebarCollapsedControl"] {
        display: none !important;
        visibility: hidden !important;
        pointer-events: none !important;
    }
    /* Disable Streamlit's native resize handle */
    [data-testid="stSidebar"]::after,
    [data-testid="stSidebar"] [data-testid="stSidebarResizeHandle"] {
        display: none !important;
        pointer-events: none !important;
    }
    [data-testid="stSidebar"] {
        resize: none !important;
    }
    .sidebar-title {
        font-size: 14px; font-weight: 600; color: #2c3e50;
        padding: 2px 0 2px 0; margin: 0; border-bottom: none;
    }
    .sidebar-hint { font-size: 12px; color: #888; font-weight: normal; }
    
    /* Sidebar button - thinner */
    [data-testid="stSidebar"] .stButton > button {
        padding: 2px 8px !important;
        min-height: 30px !important;
        height: 30px !important;
        font-size: 13px !important;
        margin-top: 2px !important;
    }
    
    /* Pull sidebar content to very top - aggressive reset */
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] > div,
    [data-testid="stSidebar"] > div > div,
    [data-testid="stSidebar"] > div > div > div,
    [data-testid="stSidebar"] > div > div > div > div,
    [data-testid="stSidebar"] [data-testid="stSidebarContent"],
    [data-testid="stSidebarContent"] > div,
    [data-testid="stSidebarContent"] > div > div,
    [data-testid="stSidebar"] [data-testid="stSidebarUserContent"],
    [data-testid="stSidebarUserContent"] > div,
    [data-testid="stSidebarUserContent"] > div > div,
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"],
    [data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"],
    [data-testid="stSidebar"] .block-container,
    [data-testid="stSidebar"] [data-testid="stSidebarNavItems"],
    [data-testid="stSidebar"] [data-testid="stSidebarNav"],
    [data-testid="stSidebar"] header {
        padding-top: 0 !important;
        margin-top: 0 !important;
    }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 4px !important;
    }
    /* Hide any header inside sidebar that creates top space */
    [data-testid="stSidebar"] [data-testid="stHeader"],
    [data-testid="stSidebar"] header {
        display: none !important;
        height: 0 !important;
    }

    /* ===== COMPACT CARDS — floating fixed panels ===== */
    [data-testid="stForm"] {
        background: white !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08) !important;
        height: auto !important;
        overflow: visible !important;
    }
    /* Compact form submit buttons — raised up */
    [data-testid="stForm"] [data-testid="stFormSubmitButton"] button {
        padding: 2px 10px !important;
        min-height: 26px !important;
        height: 26px !important;
        font-size: 12px !important;
        margin-top: -4px !important;
    }
    /* Hide dummy submit button in EVENT OUTPUT card */
    [data-testid="stForm"]:has(.eco-marker) [data-testid="stFormSubmitButton"] {
        display: none !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    /* Reduce column gap in cards for tighter label-input spacing */
    [data-testid="stForm"] [data-testid="stHorizontalBlock"] {
        gap: 0.3rem !important;
    }
    /* Event Card markers (hidden, used by JS to find the forms) */
    .eco-marker, .eci-marker { display: none; height: 0; margin: 0; padding: 0; }
    /* Event Card section headers */
    .ec-section {
        display: flex;
        gap: 4px;
        margin: 2px 0 1px 0;
        overflow: visible;
        min-height: 20px;
    }
    .ec-section-hdr {
        font-size: 10px;
        font-weight: 700;
        color: #fff;
        background: #2c3e50;
        padding: 3px 6px;
        border-radius: 2px;
        flex: 1;
        text-align: center;
        line-height: 14px;
        min-height: 18px;
        overflow: visible;
    }
    .ec-sub-hdr {
        font-size: 13px;
        font-weight: 600;
        color: #2c3e50;
        background: #ecf0f1;
        padding: 1px 4px;
        text-align: center;
        border-radius: 2px;
    }
    /* Event Card read-only output value */
    .ec-out {
        font-size: 12px;
        font-weight: 600;
        color: #2c3e50;
        background: #eaf2fb;
        border: 1px solid #b8d4f0;
        border-radius: 2px;
        padding: 1px 4px;
        height: 24px;
        line-height: 22px;
        text-align: center;
        white-space: nowrap;
        overflow: hidden;
    }
    .ec-out.empty { color: #bbb; }
    /* Event Card row label */
    .ec-lbl {
        font-size: 10px;
        font-weight: 600;
        color: #2c3e50;
        padding: 1px 3px;
        line-height: 24px;
        white-space: nowrap;
        background: #f0f4f8;
        border: 1px solid #dde;
        border-radius: 2px;
        text-align: right;
        overflow: visible;
    }
    /* Ensure Event Card column cells and markdown don't clip labels/headers */
    .eci-marker ~ div [data-testid="stHorizontalBlock"] [data-testid="stColumn"] {
        overflow: visible !important;
    }
    .eci-marker ~ div [data-testid="stHorizontalBlock"] [data-testid="stColumn"] > div {
        overflow: visible !important;
    }
    [data-testid="stForm"]:has(.eci-marker) [data-testid="stMarkdown"] {
        overflow: visible !important;
    }
    [data-testid="stForm"]:has(.eci-marker) [data-testid="stMarkdown"] > div {
        overflow: visible !important;
    }
    [data-testid="stForm"]:has(.eci-marker) [data-testid="stElementContainer"] {
        overflow: visible !important;
    }
    /* Full overflow-visible chain inside EVENT INPUT form */
    [data-testid="stForm"]:has(.eci-marker) [data-testid="stVerticalBlock"] {
        overflow: visible !important;
    }
    [data-testid="stForm"]:has(.eci-marker) [data-testid="stVerticalBlockBorderWrapper"] {
        overflow: visible !important;
    }
    [data-testid="stForm"]:has(.eci-marker) .stMarkdown {
        overflow: visible !important;
    }
    [data-testid="stForm"]:has(.eci-marker) > div {
        overflow: visible !important;
    }
    [data-testid="stForm"]:has(.eci-marker) > div > div {
        overflow: visible !important;
    }
    /* Card drag handle bar */
    .card-drag-bar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: #3498db;
        color: white;
        padding: 2px 8px;
        margin: -8px -12px 4px -12px;
        border-radius: 4px 4px 0 0;
        cursor: move;
        font-size: 12px;
        font-weight: 600;
        user-select: none;
    }
    .card-drag-bar .lock-btn {
        background: none;
        border: 1px solid rgba(255,255,255,0.5);
        color: white;
        padding: 1px 6px;
        border-radius: 3px;
        cursor: pointer;
        font-size: 11px;
    }
    .card-drag-bar .lock-btn:hover {
        background: rgba(255,255,255,0.2);
    }
    .card-drag-bar .lock-btn.locked {
        background: #e74c3c;
        border-color: #e74c3c;
    }
    
    /* Ultra-compact text inputs inside form */
    [data-testid="stForm"] .stTextInput,
    [data-testid="stForm"] .stSelectbox {
        margin-bottom: 0px !important;
        margin-top: 0px !important;
    }
    
    [data-testid="stForm"] .stTextInput > div > div > input {
        padding: 1px 4px !important;
        font-size: 13px !important;
        height: 24px !important;
        min-height: 24px !important;
        border-radius: 2px !important;
    }
    
    [data-testid="stForm"] .stSelectbox > div > div {
        font-size: 13px !important;
        min-height: 24px !important;
    }
    [data-testid="stForm"] .stSelectbox > div > div > div {
        padding: 1px 4px !important;
    }
    
    /* Card label cells */
    .card-label {
        font-size: 12px;
        font-weight: 600;
        color: #2c3e50;
        padding: 2px 3px;
        line-height: 24px;
        white-space: nowrap;
        background: #f0f4f8;
        border: 1px solid #dde;
        border-radius: 2px;
        text-align: right;
        width: 92px;
        min-width: 92px;
        max-width: 92px;
    }
    
    .card-row2-label {
        font-size: 12px;
        font-weight: 600;
        color: #7f8c8d;
        padding: 2px 3px;
        width: 92px;
        min-width: 92px;
        max-width: 92px;
        line-height: 24px;
        white-space: nowrap;
        background: #f8f8f8;
        border: 1px solid #eee;
        border-radius: 2px;
        text-align: right;
    }
    
    .card-header-right {
        font-size: 14px; font-weight: 700; color: #2c3e50;
        padding: 4px 0; margin-bottom: 4px;
    }
    
    /* Button styling */
    .stButton > button, [data-testid="stForm"] button {
        font-size: 13px !important;
    }
    
    .stDataFrame { font-size: 13px; }
    /* EVENT INPUT table scaling/containment */
    [data-testid="stForm"]:has(.eci-marker) [data-testid="stDataFrame"] {
        width: 100% !important;
        max-width: 100% !important;
        overflow-x: auto !important;
    }
    [data-testid="stForm"]:has(.eci-marker) [data-testid="stDataFrame"] > div {
        max-width: 100% !important;
    }
    [data-testid="stForm"]:has(.eci-marker) [data-testid="stDataFrame"] [role="grid"] {
        width: 100% !important;
    }
    /* EVENT INPUT: hide data_editor column names row (title rows already present) */
    [data-testid="stForm"]:has(.eci-marker) [data-testid="stDataFrame"] [role="columnheader"] {
        display: none !important;
    }
    [data-testid="stForm"]:has(.eci-marker) [data-testid="stDataFrame"] [role="row"]:has([role="columnheader"]) {
        display: none !important;
        min-height: 0 !important;
        height: 0 !important;
    }
    .eci-titlebar {
        font-size: 10px;
        font-weight: 700;
        color: #fff;
        background: #2c3e50;
        padding: 3px 6px;
        border-radius: 2px;
        text-align: center;
        margin: 2px 0 2px 0;
        line-height: 14px;
    }
    
    /* Kill vertical gaps between column rows inside form */
    [data-testid="stForm"] [data-testid="stHorizontalBlock"] {
        gap: 2px !important;
        margin-bottom: -10px !important;
    }
    
    /* Compact vertical block gaps */
    [data-testid="stForm"] [data-testid="stVerticalBlockBorderWrapper"] {
        gap: 0px !important;
    }
    [data-testid="stForm"] .stVerticalBlock {
        gap: 0px !important;
    }
    [data-testid="stForm"] [data-testid="stVerticalBlock"] {
        gap: 0px !important;
    }
    [data-testid="stForm"] [data-testid="column"] {
        padding: 0 1px !important;
    }
    /* Label columns: fixed narrow width */
    [data-testid="stForm"] [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(odd) {
        flex: 0 0 80px !important;
        min-width: 80px !important;
        max-width: 80px !important;
    }
    [data-testid="stForm"] [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(even) {
        flex: 1 1 auto !important;
    }
    
    /* Messages container - not used, kept for reference */
    
    /* Compact date input inside form */
    [data-testid="stForm"] .stDateInput > div > div > input {
        padding: 1px 4px !important;
        font-size: 13px !important;
        height: 24px !important;
        min-height: 24px !important;
    }
    [data-testid="stForm"] .stDateInput {
        margin-bottom: 0px !important;
        margin-top: 0px !important;
    }
    /* Hide dummy submit button in chart cards */
    [data-testid="stForm"]:has(.chart-card-marker) [data-testid="stFormSubmitButton"] {
        display: none !important;
        height: 0 !important;
        overflow: hidden !important;
    }
    [data-testid="stForm"]:has(.chart-card-marker) {
        overflow: hidden !important;
    }
    [data-testid="stForm"]:has(.chart-card-marker) .card-header-right {
        margin-bottom: 0 !important;
        padding: 2px 0 !important;
    }
    [data-testid="stForm"]:has(.chart-card-marker) [data-testid="stElementContainer"] {
        margin-bottom: 0 !important;
        padding-bottom: 0 !important;
    }
    [data-testid="stForm"]:has(.chart-card-marker) [data-testid="stVegaLiteChart"],
    [data-testid="stForm"]:has(.chart-card-marker) .vega-embed,
    [data-testid="stForm"]:has(.chart-card-marker) canvas,
    [data-testid="stForm"]:has(.chart-card-marker) svg {
        max-width: 100% !important;
        overflow: hidden !important;
    }
    .chart-card-marker { display: none; height: 0; }

    /* ===== FUEL TYPE COLOUR BANDS ===== */
    /* Used in Event Output, Event Input, Event Calculator tables */
    .ev-hfo, .el-hfo { background: #e8d5b8 !important; }
    .ev-do,  .el-do  { background: #fde8c8 !important; }
    .ev-oil, .el-oil { background: #ffffcc !important; }
    /* Matching colour for ec-lbl divs inside Event Input card */
    .ec-lbl-hfo { background: #e8d5b8 !important; border-color: #c8a882 !important; }
    .ec-lbl-do  { background: #fde8c8 !important; border-color: #f5c890 !important; }
    .ec-lbl-oil { background: #ffffcc !important; border-color: #e0e080 !important; }
</style>
""", unsafe_allow_html=True)

# Card-settings-dependent CSS overrides (reads from card_settings.json)
# NOTE: card-specific widths, borders, zoom are applied per-card by JS — NOT here.
st.markdown(f"""
<style>
    .eco-marker {{ display: none; height: 0; }}
    .eci-marker {{ display: none; height: 0; }}
    .ec-section-hdr {{
        font-size: {_eci_s.get('section_header_font','10px')} !important;
    }}
    .ec-out {{
        font-size: {_eco_s.get('output_value_font','12px')} !important;
    }}
    .ec-lbl {{
        font-size: {_eci_s.get('input_label_font','10px')} !important;
    }}
    /* Resize handle triangle */
    .card-resize-handle {{
        position: absolute;
        bottom: 0; right: 0;
        width: 16px; height: 16px;
        cursor: nwse-resize;
        z-index: 200;
        background: linear-gradient(135deg, transparent 50%, #3498db 50%);
        border-radius: 0 0 4px 0;
        opacity: 0.6;
    }}
    .card-resize-handle:hover {{ opacity: 1; }}
</style>
""", unsafe_allow_html=True)

# JavaScript: custom resize handle (blue dot) — bypasses Streamlit's resize entirely
import streamlit.components.v1 as components
_main_js = """
<script>
(function() {
    const doc = window.parent.document;
    const MIN_W = 300;
    const MAX_W_PCT = 0.70;
    const DEFAULT_W = 400;
    
    function init() {
        const sb = doc.querySelector('[data-testid="stSidebar"]');
        if (!sb || doc.getElementById('custom-resize-handle')) return;
        
        // Set initial width
        sb.style.width = DEFAULT_W + 'px';
        sb.style.minWidth = MIN_W + 'px';
        sb.style.maxWidth = (window.parent.innerWidth * MAX_W_PCT) + 'px';
        sb.style.transition = 'none';
        
        // Kill only Streamlit's native sidebar resize handle
        const nativeHandles = sb.querySelectorAll('[data-testid="stSidebarResizeHandle"]');
        nativeHandles.forEach(h => {
            h.style.display = 'none';
            h.style.pointerEvents = 'none';
        });
        
        // Create our custom blue dot handle
        const handle = doc.createElement('div');
        handle.id = 'custom-resize-handle';
        handle.style.cssText = `
            position: fixed;
            top: 50%;
            transform: translateY(-50%);
            width: 12px;
            height: 40px;
            background: #3498db;
            border-radius: 6px;
            cursor: col-resize;
            z-index: 10000;
            opacity: 0.7;
            transition: opacity 0.2s, height 0.2s;
            box-shadow: 0 0 4px rgba(0,0,0,0.3);
        `;
        
        function positionHandle() {
            const rect = sb.getBoundingClientRect();
            handle.style.left = (rect.right - 6) + 'px';
        }
        
        handle.addEventListener('mouseenter', () => {
            handle.style.opacity = '1';
            handle.style.height = '60px';
        });
        handle.addEventListener('mouseleave', () => {
            if (!dragging) {
                handle.style.opacity = '0.7';
                handle.style.height = '40px';
            }
        });
        
        doc.body.appendChild(handle);
        positionHandle();
        
        // Drag logic
        let dragging = false;
        
        handle.addEventListener('mousedown', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dragging = true;
            handle.style.opacity = '1';
            handle.style.height = '60px';
            doc.body.style.cursor = 'col-resize';
            doc.body.style.userSelect = 'none';
        });
        
        doc.addEventListener('mousemove', (e) => {
            if (!dragging) return;
            e.preventDefault();
            
            const maxW = window.parent.innerWidth * MAX_W_PCT;
            let newW = Math.max(MIN_W, Math.min(e.clientX, maxW));
            
            sb.style.width = newW + 'px';
            sb.style.minWidth = newW + 'px';
            sb.style.maxWidth = newW + 'px';
            
            // Update children
            sb.querySelectorAll(':scope > div').forEach(d => {
                d.style.maxWidth = 'none';
                d.style.width = '100%';
            });
            
            positionHandle();
        });
        
        doc.addEventListener('mouseup', () => {
            if (!dragging) return;
            dragging = false;
            handle.style.opacity = '0.7';
            handle.style.height = '40px';
            doc.body.style.cursor = '';
            doc.body.style.userSelect = '';
        });
        
        // Continuously keep sidebar visible & positioned
        setInterval(() => {
            sb.style.transform = 'none';
            sb.setAttribute('aria-expanded', 'true');
            sb.style.display = 'block';
            sb.style.visibility = 'visible';
            
            // Re-kill only Streamlit's native sidebar resize handle
            const handles = sb.querySelectorAll('[data-testid="stSidebarResizeHandle"]');
            handles.forEach(h => {
                h.style.display = 'none';
                h.style.pointerEvents = 'none';
            });
            
            // Keep children unconstrained & strip top padding
            sb.querySelectorAll(':scope > div').forEach(d => {
                d.style.maxWidth = 'none';
                d.style.width = '100%';
                d.style.paddingTop = '0px';
                d.style.marginTop = '0px';
            });
            // Nuclear option: walk ALL descendants and strip top padding/margin
            sb.querySelectorAll('div, section, header, nav, ul').forEach(el => {
                const cs = window.parent.getComputedStyle(el);
                const pt = parseFloat(cs.paddingTop);
                const mt = parseFloat(cs.marginTop);
                if (pt > 0) el.style.paddingTop = '0px';
                if (mt > 0) el.style.marginTop = '0px';
            });
            
            positionHandle();
        }, 300);
    }
    
    // Wait for sidebar to exist, then init
    const waitForSidebar = setInterval(() => {
        if (doc.querySelector('[data-testid="stSidebar"]')) {
            clearInterval(waitForSidebar);
            init();
        }
    }, 100);
})();

// Arrow keys navigate between inputs in the form (position-based)
(function() {
    const doc = window.parent.document;
    doc.addEventListener('keydown', function(e) {
        if (!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key)) return;
        const active = doc.activeElement;
        if (!active || active.tagName !== 'INPUT') return;
        const form = active.closest('[data-testid="stForm"]');
        if (!form) return;
        e.preventDefault();
        e.stopPropagation();
        const rect = active.getBoundingClientRect();
        const allInputs = Array.from(form.querySelectorAll('input:not([disabled]):not([type="hidden"])'));
        const HTOL = 50, VTOL = 5;
        let best = null, bestDist = Infinity;
        for (const inp of allInputs) {
            if (inp === active) continue;
            const r = inp.getBoundingClientRect();
            if (e.key === 'ArrowDown') {
                if (r.top <= rect.top + VTOL) continue;
                if (Math.abs(r.left - rect.left) > HTOL) continue;
                const d = r.top - rect.top;
                if (d < bestDist) { bestDist = d; best = inp; }
            } else if (e.key === 'ArrowUp') {
                if (r.top >= rect.top - VTOL) continue;
                if (Math.abs(r.left - rect.left) > HTOL) continue;
                const d = rect.top - r.top;
                if (d < bestDist) { bestDist = d; best = inp; }
            } else if (e.key === 'ArrowRight') {
                if (Math.abs(r.top - rect.top) > VTOL) continue;
                if (r.left <= rect.left + 5) continue;
                const d = r.left - rect.left;
                if (d < bestDist) { bestDist = d; best = inp; }
            } else if (e.key === 'ArrowLeft') {
                if (Math.abs(r.top - rect.top) > VTOL) continue;
                if (r.left >= rect.left - 5) continue;
                const d = rect.left - r.left;
                if (d < bestDist) { bestDist = d; best = inp; }
            }
        }
        if (best) best.focus();
    }, true);
})();

// Input UX: disable browser autosuggestions and add PLACE quick options (OL-CL / CL-OL)
(function() {
    const doc = window.parent.document;
    const DATALIST_ID = 'forobs-place-options';

    function ensurePlaceDatalist() {
        let dl = doc.getElementById(DATALIST_ID);
        if (dl) return dl;
        dl = doc.createElement('datalist');
        dl.id = DATALIST_ID;
        const o1 = doc.createElement('option');
        o1.value = 'OL-CL';
        const o2 = doc.createElement('option');
        o2.value = 'CL-OL';
        dl.appendChild(o1);
        dl.appendChild(o2);
        doc.body.appendChild(dl);
        return dl;
    }

    function paintPlaceInput(inp) {
        const v = String(inp.value || '').trim().toUpperCase();
        if (v === 'OL-CL') {
            inp.style.setProperty('background-color', '#eaf8ee', 'important');
            inp.style.setProperty('border-color', '#b7e2c0', 'important');
        } else if (v === 'CL-OL') {
            inp.style.setProperty('background-color', '#eaf3ff', 'important');
            inp.style.setProperty('border-color', '#bcd3f5', 'important');
        } else {
            inp.style.removeProperty('background-color');
            inp.style.removeProperty('border-color');
        }
    }

    function applyInputUx() {
        ensurePlaceDatalist();

        const allInputs = doc.querySelectorAll('section[data-testid="stMain"] input:not([type="hidden"])');
        allInputs.forEach((inp) => {
            inp.setAttribute('autocomplete', 'off');
            inp.setAttribute('autocorrect', 'off');
            inp.setAttribute('autocapitalize', 'off');
            inp.setAttribute('spellcheck', 'false');
            inp.setAttribute('data-lpignore', 'true');

            const aria = (inp.getAttribute('aria-label') || '').trim().toUpperCase();
            if (aria === 'PLACE') {
                inp.setAttribute('list', DATALIST_ID);
                if (!inp.dataset.placeUxBound) {
                    inp.addEventListener('input', () => paintPlaceInput(inp));
                    inp.addEventListener('change', () => paintPlaceInput(inp));
                    inp.dataset.placeUxBound = '1';
                }
                paintPlaceInput(inp);
            }
        });
    }

    applyInputUx();
    setInterval(applyInputUx, 800);
})();
</script>
"""
components.html(_main_js, height=0)

# Card drag-and-drop positioning system (7 cards) with zoom-resize
_eco_l = _card_layout['event_card_output']
_eci_l = _card_layout['event_card_input']
_inp_l = _card_layout['input_card']
_func_l = _card_layout['functions_panel']
_sett_l = _card_layout.get('settings_panel', {'top': 770, 'right': 19, 'locked': False})
_me_chart_l = _card_layout['me_sfoc_chart']
_dg_chart_l = _card_layout['dg_chart']
_sett_s = CARD_S.get('settings_panel', {})
_card_pos_js = """<script>
(function(){
    var doc = window.parent.document, win = window.parent;
    if (win.__cardDragCleanup) win.__cardDragCleanup();

    // Card configuration from card_settings.json
    var CFG = {
        event_card_output: {
            baseW: __ECO_BASE_W__, minZ: __ECO_MIN_Z__, maxZ: __ECO_MAX_Z__, defZ: __ECO_DEF_Z__,
            border: '__ECO_BORDER__', borderRadius: '__ECO_BORDER_RADIUS__', padding: '__ECO_PADDING__'
        },
        event_card_input: {
            baseW: __ECI_BASE_W__, minZ: __ECI_MIN_Z__, maxZ: __ECI_MAX_Z__, defZ: __ECI_DEF_Z__,
            border: '__ECI_BORDER__', borderRadius: '__ECI_BORDER_RADIUS__', padding: '__ECI_PADDING__'
        },
        input_card: {
            baseW: __INP_BASE_W__, minZ: __INP_MIN_Z__, maxZ: __INP_MAX_Z__, defZ: __INP_DEF_Z__,
            border: '__INP_BORDER__', borderRadius: '__INP_BORDER_RADIUS__', padding: '__INP_PADDING__'
        },
        functions_panel: {
            baseW: __INP_BASE_W__, minZ: __INP_MIN_Z__, maxZ: __INP_MAX_Z__, defZ: __INP_DEF_Z__,
            border: '__INP_BORDER__', borderRadius: '__INP_BORDER_RADIUS__', padding: '__INP_PADDING__'
        },
        settings_panel: {
            baseW: __SETT_BASE_W__, minZ: __SETT_MIN_Z__, maxZ: __SETT_MAX_Z__, defZ: __SETT_DEF_Z__,
            border: '__SETT_BORDER__', borderRadius: '__SETT_BORDER_RADIUS__', padding: '__SETT_PADDING__'
        },
        me_sfoc_chart: {
            baseW: __INP_BASE_W__, minZ: __INP_MIN_Z__, maxZ: __INP_MAX_Z__, defZ: __INP_DEF_Z__,
            border: '__INP_BORDER__', borderRadius: '__INP_BORDER_RADIUS__', padding: '__INP_PADDING__'
        },
        dg_chart: {
            baseW: __INP_BASE_W__, minZ: __INP_MIN_Z__, maxZ: __INP_MAX_Z__, defZ: __INP_DEF_Z__,
            border: '__INP_BORDER__', borderRadius: '__INP_BORDER_RADIUS__', padding: '__INP_PADDING__'
        }
    };

    var DEFS = {
        event_card_output: {top: __ECO_TOP__, right: __ECO_RIGHT__, locked: __ECO_LOCKED__, zoom: CFG.event_card_output.defZ},
        event_card_input:  {top: __ECI_TOP__, right: __ECI_RIGHT__, locked: __ECI_LOCKED__, zoom: CFG.event_card_input.defZ},
        input_card:        {top: __INP_TOP__, right: __INP_RIGHT__, locked: __INP_LOCKED__, zoom: CFG.input_card.defZ},
        functions_panel:   {top: __FUNC_TOP__, right: __FUNC_RIGHT__, locked: __FUNC_LOCKED__, zoom: CFG.functions_panel.defZ},
        settings_panel:    {top: __SETT_TOP__, right: __SETT_RIGHT__, locked: __SETT_LOCKED__, zoom: CFG.settings_panel.defZ},
        me_sfoc_chart:     {top: __ME_CH_TOP__, right: __ME_CH_RIGHT__, locked: __ME_CH_LOCKED__, zoom: CFG.me_sfoc_chart.defZ},
        dg_chart:          {top: __DG_CH_TOP__, right: __DG_CH_RIGHT__, locked: __DG_CH_LOCKED__, zoom: CFG.dg_chart.defZ}
    };

    function loadPos() {
        if (win.__cardPos) return win.__cardPos;
        try {
            var s = win.localStorage.getItem('cardPos');
            if (s) {
                var p = JSON.parse(s);
                if (!p.event_card_output || !p.event_card_input || !p.input_card) {
                    p = JSON.parse(JSON.stringify(DEFS));
                }
                // Ensure zoom field exists (migration)
                for (var k in DEFS) {
                    if (!p[k]) p[k] = JSON.parse(JSON.stringify(DEFS[k]));
                    if (p[k].zoom === undefined) p[k].zoom = DEFS[k].zoom;
                    var cfg = CFG[k];
                    var z = Number(p[k].zoom);
                    if (!isFinite(z)) z = DEFS[k].zoom;
                    p[k].zoom = Math.max(cfg.minZ, Math.min(cfg.maxZ, z));
                }
                win.__cardPos = p;
                return p;
            }
        } catch(e) {}
        var d = JSON.parse(JSON.stringify(DEFS));
        win.__cardPos = d;
        return d;
    }

    function savePos(p) {
        win.__cardPos = p;
        try { win.localStorage.setItem('cardPos', JSON.stringify(p)); } catch(e) {}
    }

    var drag = null, resize = null;

    function scaledWidth(cfg, zoom) {
        return Math.round(cfg.baseW * zoom);
    }

    function syncCardPos(form, p) {
        var r = form.getBoundingClientRect();
        p.top = Math.max(0, Math.round(r.top));
        p.right = Math.max(0, Math.round(doc.documentElement.clientWidth - r.right));
    }

    function onMove(e) {
        var cx = e.touches ? e.touches[0].clientX : e.clientX;
        var cy = e.touches ? e.touches[0].clientY : e.clientY;

        if (resize) {
            // Resize from left-anchored card so handle follows cursor naturally
            var newW = resize.w0 + (cx - resize.sx);
            var cfg = CFG[resize.key];
            var z = newW / cfg.baseW;
            z = Math.max(cfg.minZ, Math.min(cfg.maxZ, z));
            resize.p.zoom = z;
            resize.f.style.transform = 'scale(' + z + ')';
            // Update label in bar
            var zl = resize.f.querySelector('.zoom-label');
            if (zl) zl.textContent = Math.round(z * 100) + '%';
            return;
        }

        if (drag) {
            drag.p.top = Math.max(0, drag.t0 + cy - drag.sy);
            drag.p.left = Math.max(0, drag.l0 + (cx - drag.sx));
            drag.f.style.top = drag.p.top + 'px';
            drag.f.style.left = drag.p.left + 'px';
        }
    }

    function onUp() {
        if (resize) {
            syncCardPos(resize.f, resize.p);
            savePos(win.__cardPos);
            resize = null;
            return;
        }
        if (drag) {
            drag.f.style.zIndex = '100';
            syncCardPos(drag.f, drag.p);
            savePos(win.__cardPos);
            drag = null;
        }
    }

    doc.addEventListener('mousemove', onMove);
    doc.addEventListener('mouseup', onUp);
    doc.addEventListener('touchmove', onMove, {passive: false});
    doc.addEventListener('touchend', onUp);

    win.__cardDragCleanup = function() {
        doc.removeEventListener('mousemove', onMove);
        doc.removeEventListener('mouseup', onUp);
        doc.removeEventListener('touchmove', onMove);
        doc.removeEventListener('touchend', onUp);
    };

    function setupCard(form, key, allPos) {
        var p = allPos[key];
        var cfg = CFG[key];

        // Basic positioning — must use setProperty with important to override CSS
        form.style.setProperty('position', 'fixed', 'important');
        // Settings panel floats on top of all other cards
        form.style.zIndex = (key === 'settings_panel') ? '200' : '100';
        form.style.top = p.top + 'px';
        form.style.right = 'auto';

        // Apply card-specific styling (border, padding, width)
        form.style.setProperty('height', 'auto', 'important');
        form.style.setProperty('max-height', 'none', 'important');
        form.style.setProperty('overflow', 'visible', 'important');
        form.style.setProperty('border', cfg.border, 'important');
        form.style.setProperty('border-radius', cfg.borderRadius, 'important');
        form.style.setProperty('padding', cfg.padding, 'important');

        // Apply 2D scaling to whole card while keeping left-anchored positioning
        var appliedZoom = Number(p.zoom);
        if (!isFinite(appliedZoom)) appliedZoom = cfg.defZ;
        appliedZoom = Math.max(cfg.minZ, Math.min(cfg.maxZ, appliedZoom));
        p.zoom = appliedZoom;
        var w = scaledWidth(cfg, appliedZoom);
        form.style.setProperty('width', cfg.baseW + 'px', 'important');
        form.style.setProperty('max-width', cfg.baseW + 'px', 'important');
        form.style.transformOrigin = 'top left';
        form.style.transform = 'scale(' + appliedZoom + ')';
        var vpW = doc.documentElement.clientWidth;
        p.left = Math.max(0, vpW - (p.right || 0) - w);
        form.style.left = p.left + 'px';

        // Ensure parents don't clip
        var parent = form.parentElement;
        while (parent && parent !== doc.body) {
            parent.style.overflow = 'visible';
            parent = parent.parentElement;
        }

        if (form.querySelector('.card-drag-bar')) return;

        var origH = form.querySelector('.card-header-right');
        var fallbacks = {
            event_card_output:'EVENT OUTPUT',
            event_card_input:'EVENT INPUT',
            input_card:'INPUT CARD',
            me_sfoc_chart:'ME SFOC [g/kWh]',
            dg_chart:'DG [mT/h]'
        };
        var fallback = fallbacks[key] || key;
        var title = origH ? origH.textContent.trim() : fallback;
        if (origH) origH.style.display = 'none';

        // Drag bar with title, zoom label, lock button
        var bar = doc.createElement('div');
        bar.className = 'card-drag-bar';

        var lbl = doc.createElement('span');
        lbl.textContent = title;

        var zoomLbl = doc.createElement('span');
        zoomLbl.className = 'zoom-label';
        zoomLbl.style.cssText = 'font-size:9px;opacity:0.8;margin-left:6px;font-weight:400;';
        zoomLbl.textContent = Math.round((p.zoom || cfg.defZ) * 100) + '%';

        var btn = doc.createElement('button');
        btn.className = 'lock-btn' + (p.locked ? ' locked' : '');
        btn.innerHTML = p.locked ? '&#128274;' : '&#128275;';
        btn.title = 'Lock / Unlock position & resize';

        var leftGrp = doc.createElement('span');
        leftGrp.appendChild(lbl);
        leftGrp.appendChild(zoomLbl);
        bar.appendChild(leftGrp);
        bar.appendChild(btn);
        form.insertBefore(bar, form.firstChild);

        // Resize handle (bottom-right triangle)
        form.style.position = 'fixed'; // ensure relative for handle
        var rh = doc.createElement('div');
        rh.className = 'card-resize-handle';
        form.appendChild(rh);

        rh.addEventListener('mousedown', function(e) {
            if (p.locked) return;
            e.preventDefault(); e.stopPropagation();
            var rect = form.getBoundingClientRect();
            resize = {
                f: form, p: p, key: key,
                sx: e.clientX, w0: rect.width
            };
        });
        rh.addEventListener('touchstart', function(e) {
            if (p.locked) return;
            e.preventDefault(); e.stopPropagation();
            var rect = form.getBoundingClientRect();
            resize = {
                f: form, p: p, key: key,
                sx: e.touches[0].clientX, w0: rect.width
            };
        }, {passive: false});

        // Lock button
        btn.addEventListener('click', function(ev) {
            ev.preventDefault(); ev.stopPropagation();
            p.locked = !p.locked;
            btn.className = 'lock-btn' + (p.locked ? ' locked' : '');
            btn.innerHTML = p.locked ? '&#128274;' : '&#128275;';
            savePos(allPos);
        });

        // Drag from bar
        function startDrag(e) {
            if (p.locked) return;
            if (e.target === btn || (e.target.closest && e.target.closest('.lock-btn'))) return;
            if (e.target === rh || (e.target.closest && e.target.closest('.card-resize-handle'))) return;
            var cx = e.touches ? e.touches[0].clientX : e.clientX;
            var cy = e.touches ? e.touches[0].clientY : e.clientY;
            var r = form.getBoundingClientRect();
            drag = {
                f: form, p: p, sx: cx, sy: cy,
                t0: r.top, l0: r.left
            };
            form.style.zIndex = '150';
            e.preventDefault();
        }
        bar.addEventListener('mousedown', startDrag);
        bar.addEventListener('touchstart', startDrag, {passive: false});
    }

    function init() {
        var main = doc.querySelector('section[data-testid="stMain"]');
        if (!main) return false;
        var forms = main.querySelectorAll('[data-testid="stForm"]');
        if (forms.length < 5) return false;
        var pos = loadPos(), ok = 0;
        for (var i = 0; i < forms.length; i++) {
            var h = forms[i].querySelector('.card-header-right');
            if (!h) continue;
            var t = h.textContent || '';
            if (t.indexOf('EVENT OUTPUT') >= 0) { setupCard(forms[i], 'event_card_output', pos); ok++; }
            else if (t.indexOf('EVENT INPUT') >= 0) { setupCard(forms[i], 'event_card_input', pos); ok++; }
            else if (t.indexOf('INPUT CARD') >= 0) { setupCard(forms[i], 'input_card', pos); ok++; }
            else if (t.indexOf('FUNCTIONS PANEL') >= 0) { setupCard(forms[i], 'functions_panel', pos); ok++; }
            else if (t.indexOf('SETTINGS') >= 0) { setupCard(forms[i], 'settings_panel', pos); ok++; }
            else if (t.indexOf('ME SFOC CHART') >= 0 || t.indexOf('SFOC [g/kWh]') >= 0 || t.indexOf('ME SFOC [g/kWh]') >= 0) { setupCard(forms[i], 'me_sfoc_chart', pos); ok++; }
            else if (t.indexOf('DG CONSUMPTION CHART') >= 0 || t.indexOf('DG [mT/h]') >= 0) { setupCard(forms[i], 'dg_chart', pos); ok++; }
        }
        // Apply DEP lock if active
        applyDepLock(main);
        return ok >= 5;
    }

    // ── DEP M/E counter lock ──────────────────────────────────────────────
    // When EVENT selectbox = DEPARTURE and dep-lock-data[data-dep-active]="1",
    // fill M/E counter inputs with previous event values and make them read-only.
    var _depLockApplied = false;

    function applyDepLock(main) {
        var lockDiv = main ? main.querySelector('.dep-lock-data') : null;
        if (!lockDiv) return;
        if (lockDiv.getAttribute('data-dep-active') !== '1') {
            // Remove any previously applied lock
            _unlockDepFields(main);
            return;
        }
        // Find the EVENT selectbox in the INPUT CARD form
        var inputForm = null;
        var forms = main.querySelectorAll('[data-testid="stForm"]');
        for (var i = 0; i < forms.length; i++) {
            var h = forms[i].querySelector('.card-header-right');
            if (h && h.textContent.indexOf('INPUT CARD') >= 0) { inputForm = forms[i]; break; }
        }
        if (!inputForm) return;

        // Watch the EVENT selectbox for DEPARTURE
        var eventSel = null;
        var allSel = inputForm.querySelectorAll('[data-baseweb="select"] [data-testid="stSelectbox"]');
        // Try finding via aria-label containing 'EVENT'
        var allInputs = inputForm.querySelectorAll('input');
        // Streamlit renders selectbox as a div with current value text
        // We check the selected value text in the select box wrapper
        var selectWrappers = inputForm.querySelectorAll('[data-baseweb="select"]');
        var isDep = false;
        for (var j = 0; j < selectWrappers.length; j++) {
            var txt = selectWrappers[j].textContent || '';
            if (txt.indexOf('DEPARTURE') >= 0) { isDep = true; break; }
        }
        if (!isDep) {
            _unlockDepFields(main);
            return;
        }
        // Lock M/E counter fields
        var prevVals = {
            'ME REV C': lockDiv.getAttribute('data-me-rev-c') || '',
            'MAIN FLMTR': lockDiv.getAttribute('data-main-flmtr') || '',
            'CYL OIL COUNT': lockDiv.getAttribute('data-cyl-oil-count') || '',
            'ME PWRMTR': lockDiv.getAttribute('data-me-pwrmtr') || '',
            'M/E HRS': lockDiv.getAttribute('data-me-hrs') || ''
        };
        var inps = inputForm.querySelectorAll('input[aria-label]');
        for (var k = 0; k < inps.length; k++) {
            var lbl = (inps[k].getAttribute('aria-label') || '').trim().toUpperCase();
            if (prevVals.hasOwnProperty(lbl)) {
                inps[k].setAttribute('readonly', 'readonly');
                inps[k].style.setProperty('background-color', '#f0f0f0', 'important');
                inps[k].style.setProperty('color', '#888', 'important');
                inps[k].style.setProperty('cursor', 'not-allowed', 'important');
                inps[k].dataset.depLocked = '1';
            }
        }
        _depLockApplied = true;
    }

    function _unlockDepFields(main) {
        if (!_depLockApplied) return;
        if (!main) return;
        var inps = main.querySelectorAll('input[data-dep-locked="1"]');
        for (var i = 0; i < inps.length; i++) {
            inps[i].removeAttribute('readonly');
            inps[i].style.removeProperty('background-color');
            inps[i].style.removeProperty('color');
            inps[i].style.removeProperty('cursor');
            delete inps[i].dataset.depLocked;
        }
        _depLockApplied = false;
    }

    var poll = setInterval(function() { if (init()) clearInterval(poll); }, 150);
    // Re-apply DEP lock on every poll tick (handles selectbox changes)
    setInterval(function() {
        var main = doc.querySelector('section[data-testid="stMain"]');
        if (main) applyDepLock(main);
    }, 500);
})();
</script>"""
# Event Card Output settings
_card_pos_js = _card_pos_js.replace('__ECO_BASE_W__', str(_eco_s.get('base_width', 520)))
_card_pos_js = _card_pos_js.replace('__ECO_MIN_Z__', str(_eco_s.get('min_zoom', 1.0)))
_card_pos_js = _card_pos_js.replace('__ECO_MAX_Z__', str(_eco_s.get('max_zoom', 1.8)))
_card_pos_js = _card_pos_js.replace('__ECO_DEF_Z__', str(_eco_s.get('default_zoom', 1.0)))
_card_pos_js = _card_pos_js.replace('__ECO_BORDER__', _eco_s.get('border', '2px solid #2c3e50'))
_card_pos_js = _card_pos_js.replace('__ECO_BORDER_RADIUS__', _eco_s.get('border_radius', '6px'))
_card_pos_js = _card_pos_js.replace('__ECO_PADDING__', _eco_s.get('padding', '8px 12px 14px 12px'))
_card_pos_js = _card_pos_js.replace('__ECO_TOP__', str(_eco_l['top']))
_card_pos_js = _card_pos_js.replace('__ECO_RIGHT__', str(_eco_l['right']))
_card_pos_js = _card_pos_js.replace('__ECO_LOCKED__', str(_eco_l['locked']).lower())
# Event Card Input settings
_card_pos_js = _card_pos_js.replace('__ECI_BASE_W__', str(_eci_s.get('base_width', 520)))
_card_pos_js = _card_pos_js.replace('__ECI_MIN_Z__', str(_eci_s.get('min_zoom', 1.0)))
_card_pos_js = _card_pos_js.replace('__ECI_MAX_Z__', str(_eci_s.get('max_zoom', 1.8)))
_card_pos_js = _card_pos_js.replace('__ECI_DEF_Z__', str(_eci_s.get('default_zoom', 1.0)))
_card_pos_js = _card_pos_js.replace('__ECI_BORDER__', _eci_s.get('border', '2px solid #3498db'))
_card_pos_js = _card_pos_js.replace('__ECI_BORDER_RADIUS__', _eci_s.get('border_radius', '6px'))
_card_pos_js = _card_pos_js.replace('__ECI_PADDING__', _eci_s.get('padding', '8px 12px 14px 12px'))
_card_pos_js = _card_pos_js.replace('__ECI_TOP__', str(_eci_l['top']))
_card_pos_js = _card_pos_js.replace('__ECI_RIGHT__', str(_eci_l['right']))
_card_pos_js = _card_pos_js.replace('__ECI_LOCKED__', str(_eci_l['locked']).lower())
# Input Card settings
_card_pos_js = _card_pos_js.replace('__INP_BASE_W__', str(_inp_s.get('base_width', 480)))
_card_pos_js = _card_pos_js.replace('__INP_MIN_Z__', str(_inp_s.get('min_zoom', 1.0)))
_card_pos_js = _card_pos_js.replace('__INP_MAX_Z__', str(_inp_s.get('max_zoom', 1.8)))
_card_pos_js = _card_pos_js.replace('__INP_DEF_Z__', str(_inp_s.get('default_zoom', 1.0)))
_card_pos_js = _card_pos_js.replace('__INP_BORDER__', _inp_s.get('border', '2px solid #3498db'))
_card_pos_js = _card_pos_js.replace('__INP_BORDER_RADIUS__', _inp_s.get('border_radius', '6px'))
_card_pos_js = _card_pos_js.replace('__INP_PADDING__', _inp_s.get('padding', '8px 12px 14px 12px'))
_card_pos_js = _card_pos_js.replace('__INP_TOP__', str(_inp_l['top']))
_card_pos_js = _card_pos_js.replace('__INP_RIGHT__', str(_inp_l['right']))
_card_pos_js = _card_pos_js.replace('__INP_LOCKED__', str(_inp_l['locked']).lower())
_card_pos_js = _card_pos_js.replace('__FUNC_TOP__', str(_func_l['top']))
_card_pos_js = _card_pos_js.replace('__FUNC_RIGHT__', str(_func_l['right']))
_card_pos_js = _card_pos_js.replace('__FUNC_LOCKED__', str(_func_l['locked']).lower())
_card_pos_js = _card_pos_js.replace('__SETT_BASE_W__', str(_sett_s.get('base_width', 480)))
_card_pos_js = _card_pos_js.replace('__SETT_MIN_Z__', str(_sett_s.get('min_zoom', 1.0)))
_card_pos_js = _card_pos_js.replace('__SETT_MAX_Z__', str(_sett_s.get('max_zoom', 1.8)))
_card_pos_js = _card_pos_js.replace('__SETT_DEF_Z__', str(_sett_s.get('default_zoom', 1.0)))
_card_pos_js = _card_pos_js.replace('__SETT_BORDER__', _sett_s.get('border', '2px solid #2c3e50'))
_card_pos_js = _card_pos_js.replace('__SETT_BORDER_RADIUS__', _sett_s.get('border_radius', '6px'))
_card_pos_js = _card_pos_js.replace('__SETT_PADDING__', _sett_s.get('padding', '8px 12px 14px 12px'))
_card_pos_js = _card_pos_js.replace('__SETT_TOP__', str(_sett_l['top']))
_card_pos_js = _card_pos_js.replace('__SETT_RIGHT__', str(_sett_l['right']))
_card_pos_js = _card_pos_js.replace('__SETT_LOCKED__', str(_sett_l['locked']).lower())
_card_pos_js = _card_pos_js.replace('__ME_CH_TOP__', str(_me_chart_l['top']))
_card_pos_js = _card_pos_js.replace('__ME_CH_RIGHT__', str(_me_chart_l['right']))
_card_pos_js = _card_pos_js.replace('__ME_CH_LOCKED__', str(_me_chart_l['locked']).lower())
_card_pos_js = _card_pos_js.replace('__DG_CH_TOP__', str(_dg_chart_l['top']))
_card_pos_js = _card_pos_js.replace('__DG_CH_RIGHT__', str(_dg_chart_l['right']))
_card_pos_js = _card_pos_js.replace('__DG_CH_LOCKED__', str(_dg_chart_l['locked']).lower())
components.html(_card_pos_js, height=0)

# Session state initialization
if 'editing_id' not in st.session_state:
    st.session_state.editing_id = None

if 'new_entry_mode' not in st.session_state:
    st.session_state.new_entry_mode = False

if 'confirm_delete' not in st.session_state:
    st.session_state.confirm_delete = False

if 'show_settings' not in st.session_state:
    st.session_state.show_settings = False

ensure_calculated_fields_ready_once()

# Dynamic widget key suffix — forces fresh widgets when switching events
_key_suffix = f"_e{st.session_state.editing_id}" if st.session_state.editing_id else "_new"

# Event types
EVENT_TYPES = ["NOON", "STBY", "EOSP", "SOSP", "FWE", "ARRIVAL", "DEPARTURE", "SHIFTING-BEG", "SHIFTING-END", "MID"]
PLACE_PRESETS = ["SCRUBBER OL-CL", "SCRUBBER CL-OL"]

# ============ LAYOUT ============

# Determine if editing or new entry
editing_event = None
if st.session_state.editing_id is not None:
    conn = get_connection()
    result = pd.read_sql_query(f"SELECT * FROM events WHERE id = {st.session_state.editing_id}", conn)
    conn.close()
    if not result.empty:
        editing_event = result.iloc[0].to_dict()

# All numeric field keys
ALL_NUMERIC_KEYS = ['me_rev_c', 'main_flmtr', 'dg_in_flmtr', 'dg_out_flmtr', 'blr_flmtr',
                    'cyl_oil_count', 'me_pwrmtr', 'me_hrs', 'dg1_hrs', 'dg2_hrs', 'dg3_hrs',
                    'boiler_hrs', 'dg1_mwh', 'dg2_mwh', 'dg3_mwh', 'sox_co2',
                    'ocl_pp_a', 'ocl_pp_b', 'ocl_pp_c', 'phe_a', 'phe_b',
                    'sea_temp', 'st_lo_tmp', 'wcu_sep', 'comp_1', 'comp_2', 'w_comp']

# Default values - properly formatted
if editing_event:
    # Parse stored date string back to date object
    _date_str = str(editing_event.get('date', '') or '')
    try:
        _date_obj = datetime.strptime(_date_str, '%d-%m-%y').date() if _date_str else datetime.now().date()
    except ValueError:
        _date_obj = datetime.now().date()
    defaults = {
        'date': _date_obj,
        'time': str(editing_event.get('time', '') or ''),
        'event': str(editing_event.get('event', 'NOON') or 'NOON'),
        'place': str(editing_event.get('place', '') or ''),
    }
    for k in ALL_NUMERIC_KEYS:
        defaults[k] = fmt_field(k, editing_event.get(k))
else:
    # New entry - all fields empty
    defaults = {k: '' for k in ['time', 'place'] + ALL_NUMERIC_KEYS}
    defaults['date'] = datetime.now().date()
    defaults['event'] = 'NOON'

# Row 2 disabled if not MID (visual only - fields always editable)
row2_disabled = (defaults['event'] != "MID")

# ── DEP M/E counter lock: compute previous event values for JS injection ──
_app_settings_now = _load_app_settings()
_dep_active = (_app_settings_now.get('dep_stops_me_counters', 'no') == 'yes')
_dep_prev_vals = {}
if _dep_active:
    _dep_prev_vals = _get_prev_event_for_dep(st.session_state.editing_id)

# ============ FLOATING CARDS — draggable via JS, position:fixed ============
_eco_col = st.container()
_eci_col = st.container()
_inp_col = st.container()
_func_col = st.container()
_me_chart_col = st.container()
_dg_chart_col = st.container()

_chart_data_version = 'v3_dg_mtph_minutes'
if st.session_state.get('_chart_data_version') != _chart_data_version:
    rebuild_chart_data()
    st.session_state['_chart_data_version'] = _chart_data_version

_chart_points = load_chart_data()
if not _chart_points:
    rebuild_chart_data()
    _chart_points = load_chart_data()

_chart_df = pd.DataFrame(_chart_points) if _chart_points else pd.DataFrame()
_chart_time_ok = False
_x_domain_start = None
_x_domain_end = None
if not _chart_df.empty and {'id', 'date', 'time'}.issubset(set(_chart_df.columns)):
    _chart_df = _chart_df.copy()
    _chart_df['_ts'] = pd.to_datetime(
        _chart_df['date'].astype(str).str.strip() + ' ' + _chart_df['time'].astype(str).str.strip(),
        format='%d-%m-%y %H:%M',
        errors='coerce'
    )
    _chart_df = _chart_df.dropna(subset=['_ts']).sort_values('_ts')
    if not _chart_df.empty:
        _chart_time_ok = True
        _x_domain_end = _chart_df['_ts'].max()
        _x_domain_start = max(_chart_df['_ts'].min(), _x_domain_end - pd.Timedelta(days=7))
elif not _chart_df.empty and 'id' in _chart_df.columns:
    _chart_df = _chart_df.sort_values('id')

_chart_plot_df = _chart_df
if _chart_time_ok and not _chart_df.empty:
    _max_render_points = 1600
    if len(_chart_df) > _max_render_points:
        _step = int(len(_chart_df) / _max_render_points) + 1
        _chart_plot_df = _chart_df.iloc[::_step].copy()

with _me_chart_col:
    with st.form("me_sfoc_chart_form"):
        st.markdown('<div class="chart-card-marker"></div>', unsafe_allow_html=True)
        st.markdown('<div class="card-header-right">ME SFOC [g/kWh]</div>', unsafe_allow_html=True)
        if _chart_time_ok and {'_ts', 'id', 'me_sfoc_calc', 'me_sfoc_cor'}.issubset(set(_chart_plot_df.columns)):
            _me_chart = _chart_plot_df[['id', '_ts', 'me_sfoc_calc', 'me_sfoc_cor']].copy()
            for _col in ['me_sfoc_calc', 'me_sfoc_cor']:
                _me_chart[_col] = pd.to_numeric(_me_chart[_col], errors='coerce')
                _me_chart.loc[(_me_chart[_col] < 100) | (_me_chart[_col] > 300), _col] = None
            _me_chart_long = _me_chart.melt(
                id_vars=['id', '_ts'],
                value_vars=['me_sfoc_calc', 'me_sfoc_cor'],
                var_name='series',
                value_name='value'
            )
            _me_chart_long['series'] = _me_chart_long['series'].map({
                'me_sfoc_calc': 'CALCULATED [g/kWh]',
                'me_sfoc_cor': 'CORRECTED [g/kWh]'
            })
            _me_chart_long = _me_chart_long.dropna(subset=['value'])
            _me_pan = alt.selection_interval(bind='scales', encodings=['x'])
            _me_base = alt.Chart(_me_chart_long).encode(
                x=alt.X(
                    '_ts:T',
                    title=None,
                    axis=alt.Axis(labels=False, ticks=False, domain=False, grid=False),
                    scale=alt.Scale(domain=[_x_domain_start.isoformat(), _x_domain_end.isoformat()])
                ),
                y=alt.Y(
                    'value:Q',
                    title=None,
                    axis=alt.Axis(labels=True, ticks=True, domain=True, grid=True),
                    scale=alt.Scale(domain=[150, 300])
                ),
                color=alt.Color('series:N', legend=None),
                tooltip=[
                    alt.Tooltip('id:Q', title='ID'),
                    alt.Tooltip('_ts:T', title='Time'),
                    alt.Tooltip('value:Q', title='SFOC', format='.2f')
                ]
            )
            _me_alt = (_me_base.mark_line() + _me_base.mark_point(size=2)).add_params(_me_pan).properties(height=340)
            st.altair_chart(_me_alt, width='stretch')
        else:
            st.caption('No chart data yet.')
        st.form_submit_button('_', disabled=True, type='secondary')

with _dg_chart_col:
    with st.form("dg_chart_form"):
        st.markdown('<div class="chart-card-marker"></div>', unsafe_allow_html=True)
        st.markdown('<div class="card-header-right">DG [mT/h]</div>', unsafe_allow_html=True)
        if _chart_time_ok and {'_ts', 'id', 'dg_cons_calc', 'dg_cons_cor'}.issubset(set(_chart_plot_df.columns)):
            _dg_chart = _chart_plot_df[['id', '_ts', 'dg_cons_calc', 'dg_cons_cor']].copy()
            for _col in ['dg_cons_calc', 'dg_cons_cor']:
                _dg_chart[_col] = pd.to_numeric(_dg_chart[_col], errors='coerce')
                _dg_chart.loc[(_dg_chart[_col] <= 0) | (_dg_chart[_col] > 250), _col] = None
            _dg_chart_long = _dg_chart.melt(
                id_vars=['id', '_ts'],
                value_vars=['dg_cons_calc', 'dg_cons_cor'],
                var_name='series',
                value_name='value'
            )
            _dg_chart_long['series'] = _dg_chart_long['series'].map({
                'dg_cons_calc': 'CALCULATED [mT/h]',
                'dg_cons_cor': 'CORRECTED [mT/h]'
            })
            _dg_chart_long = _dg_chart_long.dropna(subset=['value'])
            _dg_pan = alt.selection_interval(bind='scales', encodings=['x'])
            _dg_base = alt.Chart(_dg_chart_long).encode(
                x=alt.X(
                    '_ts:T',
                    title=None,
                    axis=alt.Axis(labels=False, ticks=False, domain=False, grid=False),
                    scale=alt.Scale(domain=[_x_domain_start.isoformat(), _x_domain_end.isoformat()])
                ),
                y=alt.Y(
                    'value:Q',
                    title=None,
                    axis=alt.Axis(labels=True, ticks=True, domain=True, grid=True),
                    scale=alt.Scale(domain=[0, 0.2])
                ),
                color=alt.Color('series:N', legend=None),
                tooltip=[
                    alt.Tooltip('id:Q', title='ID'),
                    alt.Tooltip('_ts:T', title='Time'),
                    alt.Tooltip('value:Q', title='mT/h', format='.3f')
                ]
            )
            _dg_alt = (_dg_base.mark_line() + _dg_base.mark_point(size=3)).add_params(_dg_pan).properties(height=340)
            st.altair_chart(_dg_alt, width='stretch')
        else:
            st.caption('No chart data yet.')
        st.form_submit_button('_', disabled=True, type='secondary')

# Helper: format time input
def _fmt_time(raw):
    """Auto-format time: 1234 -> 12:34, 930 -> 09:30"""
    import re as _re
    s = str(raw).strip().replace(':', '')
    if not s:
        return ''
    if _re.match(r'^\d{3,4}$', s):
        s = s.zfill(4)
        return f"{s[:2]}:{s[2:]}"
    return str(raw).strip()

def _fmt_c2(val):
    """Format event card numeric values for display"""
    if val is None or val == '' or val == 'None':
        return ''
    try:
        v = float(val)
        if v == 0.0:
            return ''
        return f"{v:.2f}".rstrip('0').rstrip('.')
    except (ValueError, TypeError):
        return str(val)

# ---- EVENT CARD OUTPUT (read-only calculated values) ----
_ev = editing_event or {}
_eid = st.session_state.editing_id
_can_edit = bool(_eid and _eid > 1)

# Helper: format output value for display
def _ov(key, decimals=2):
    v = _ev.get(key)
    if v is None or v == '' or v == 'None':
        return '--'
    try:
        fv = float(v)
        if fv == 0.0:
            return '--'
        return f"{fv:.{decimals}f}".rstrip('0').rstrip('.')
    except (ValueError, TypeError):
        return str(v) if v else '--'

def _ov_time(key):
    v = _ev.get(key)
    if not v or v == 'None' or v == '00:00':
        return '--'
    return str(v)

# Build input-field defaults
_c2_fo_keys = ['me_fo_set', 'dg_fo_set', 'blr_fo_set']
_c2_input_keys = ['me_hfo_cor_cons', 'me_do_cor_cons',
                  'me_sys_cor_cons', 'me_cyl_cor_cons', 'dg_sys_cor_cons',
                  'hfo_bnkr', 'do_bnkr', 'me_sys_bnkr', 'me_cyl_bnkr', 'dg_sys_bnkr',
                  'me_sys_calc_cons', 'dg_sys_calc_cons']
c2_def = {}
if _can_edit:
    for k in _c2_fo_keys:
        v = _ev.get(k)
        c2_def[k] = str(v) if v and v != 'None' else 'HFO'
    for k in _c2_input_keys:
        c2_def[k] = _fmt_c2(_ev.get(k))
else:
    for k in _c2_fo_keys:
        c2_def[k] = 'HFO'
    for k in _c2_input_keys:
        c2_def[k] = ''

_eco_title = f"EVENT OUTPUT  ID_{_eid}" if _eid else "EVENT OUTPUT"
_eci_title = f"EVENT INPUT  ID_{_eid}" if _eid else "EVENT INPUT"

# Compute TTL fuel ROB for display
try:
    _hfo_rob_v = float(_ev.get('hfo_rob') or 0)
    _do_rob_v = float(_ev.get('do_rob') or 0)
except (ValueError, TypeError):
    _hfo_rob_v, _do_rob_v = 0, 0
_ttl_rob = _hfo_rob_v + _do_rob_v
_ttl_rob_s = f"{_ttl_rob:.2f}".rstrip('0').rstrip('.') if _ttl_rob > 0 else '--'

with _eco_col:
    with st.form(f"event_output_form{_key_suffix}"):
        st.markdown('<div class="eco-marker"></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="card-header-right">{_eco_title}</div>', unsafe_allow_html=True)

        # ══════ SECTIONS 1-3: all OUTPUT — rendered as HTML tables ══════
        # Compute total HFO / DO consumption for summary row
        try:
            _hfo_total = sum(float(_ev.get(k) or 0) for k in ['me_hfo_acc_cons','dg_hfo_acc_cons','blr_hfo_acc_cons'])
        except (ValueError, TypeError):
            _hfo_total = 0
        try:
            _do_total = sum(float(_ev.get(k) or 0) for k in ['me_do_acc_cons','dg_do_acc_cons','blr_do_acc_cons'])
        except (ValueError, TypeError):
            _do_total = 0
        _hfo_total_s = f"{_hfo_total:.2f}".rstrip('0').rstrip('.') if _hfo_total else '--'
        _do_total_s = f"{_do_total:.2f}".rstrip('0').rstrip('.') if _do_total else '--'

        # ── Per-DG fuel split by proportional running hours ──────────────
        def _hhmm_to_dec(v):
            """Parse 'HH:MM' string from DB → decimal hours."""
            try:
                if not v or v == 'None': return 0.0
                h, m = str(v).split(':')
                return int(h) + int(m) / 60.0
            except Exception:
                return 0.0

        def _fmt_fuel(val):
            """Format a float fuel value the same way _ov() does."""
            if val == 0.0: return '--'
            s = f"{val:.2f}".rstrip('0').rstrip('.')
            return s if s else '--'

        _dg1_dec = _hhmm_to_dec(_ev.get('dg1_diff'))
        _dg2_dec = _hhmm_to_dec(_ev.get('dg2_diff'))
        _dg3_dec = _hhmm_to_dec(_ev.get('dg3_diff'))
        _dg_total_dec = _dg1_dec + _dg2_dec + _dg3_dec

        try: _dg_hfo_total = float(_ev.get('dg_hfo_acc_cons') or 0)
        except: _dg_hfo_total = 0.0
        try: _dg_do_total = float(_ev.get('dg_do_acc_cons') or 0)
        except: _dg_do_total = 0.0

        if _dg_total_dec > 0:
            _dg1_hfo = _fmt_fuel(round(_dg_hfo_total * _dg1_dec / _dg_total_dec, 2))
            _dg2_hfo = _fmt_fuel(round(_dg_hfo_total * _dg2_dec / _dg_total_dec, 2))
            _dg3_hfo = _fmt_fuel(round(_dg_hfo_total * _dg3_dec / _dg_total_dec, 2))
            _dg1_do  = _fmt_fuel(round(_dg_do_total  * _dg1_dec / _dg_total_dec, 2))
            _dg2_do  = _fmt_fuel(round(_dg_do_total  * _dg2_dec / _dg_total_dec, 2))
            _dg3_do  = _fmt_fuel(round(_dg_do_total  * _dg3_dec / _dg_total_dec, 2))
        else:
            _dg1_hfo = _dg2_hfo = _dg3_hfo = '--'
            _dg1_do  = _dg2_do  = _dg3_do  = '--'

        _sec1_rows = ''
        for _lbl, _rk, _hv, _dv in [
            ('M/E',   'me_diff',  _ov('me_hfo_acc_cons', 2),  _ov('me_do_acc_cons', 2)),
            ('D/G#1', 'dg1_diff', _dg1_hfo,                   _dg1_do),
            ('D/G#2', 'dg2_diff', _dg2_hfo,                   _dg2_do),
            ('D/G#3', 'dg3_diff', _dg3_hfo,                   _dg3_do),
            ('BLR',   'blr_diff', _ov('blr_hfo_acc_cons', 2), _ov('blr_do_acc_cons', 2)),
        ]:
            _sec1_rows += (
                f'<tr><td class="el">{_lbl}</td><td class="ev">{_ov_time(_rk)}</td>'
                f'<td class="ev ev-hfo">{_hv}</td>'
                f'<td class="ev ev-do">{_dv}</td></tr>'
            )
        # ST_TIME row with HFO/DO totals
        _sec1_rows += (
            f'<tr><td class="el">ST_TIME</td><td class="ev">{_ov_time("st_time")}</td>'
            f'<td class="ev ev-hfo">{_hfo_total_s}</td>'
            f'<td class="ev ev-do">{_do_total_s}</td></tr>'
        )

        _sec2_rows = ''
        for _ll, _lk, _ld, _rl, _rk2, _rd in [
            ('AVG PWR [kW]', 'avg_pwr', 2, 'M/E SYS', 'me_sys_acc_cons', 2),
            ('AVG RPM [rpm]', 'avg_rpm', 2, 'M/E CYL', 'me_cyl_acc_cons', 2),
            ('TTL PWR [kWh]', 'ttl_pwr', 2, 'D/G SYS', 'dg_sys_acc_cons', 2),
            ('TTL RPM [rev]', 'ttl_rpm', 2, '',         None,              None),
        ]:
            _oil_cls = ' ev-oil' if _rk2 else ''
            _oil_lbl_cls = ' el-oil' if _rl else ''
            _sec2_rows += (
                f'<tr><td class="el">{_ll}</td><td class="ev">{_ov(_lk, _ld)}</td>'
                f'<td class="el{_oil_lbl_cls}">{_rl}</td>'
                f'<td class="ev{_oil_cls}">{_ov(_rk2, _rd) if _rk2 else ""}</td></tr>'
            )

        _sec3_rows = ''
        _fuel_type_map = {'HFO': 'hfo', 'DO': 'do'}
        for _ll, _lk, _ld, _rl, _rk2, _rd in [
            ('HFO', 'hfo_rob', 2, 'M/E SYS', 'me_sys_rob', 2),
            ('DO',  'do_rob',  2, 'M/E CYL', 'me_cyl_rob', 2),
            ('TTL', None,      0, 'D/G SYS', 'dg_sys_rob', 2),
        ]:
            _fc = _fuel_type_map.get(_ll, '')
            _fuel_lbl_cls = f' el-{_fc}' if _fc else ''
            _fuel_val_cls = f' ev-{_fc}' if _fc else ''
            _lv = _ov(_lk, _ld) if _lk else _ttl_rob_s
            _sec3_rows += (
                f'<tr><td class="el{_fuel_lbl_cls}">{_ll}</td><td class="ev{_fuel_val_cls}">{_lv}</td>'
                f'<td class="el el-oil">{_rl}</td><td class="ev ev-oil">{_ov(_rk2, _rd)}</td></tr>'
            )

        _tbl_lf = _eco_s.get('table_label_font','11px')
        _tbl_vf = _eco_s.get('table_value_font','12px')
        _tbl_hf = _eco_s.get('table_header_font','10px')
        _tbl_lw = _eco_s.get('table_label_width','22%')
        _tbl_vw = _eco_s.get('table_value_width','28%')
        _output_html = f'''
        <style>
        .ect {{width:100%;border-collapse:collapse;margin:0 0 2px 0;}}
        .ect td {{padding:2px 4px;font-size:12px;}}
        .ect .sh {{background:#2c3e50;color:#fff;font-weight:700;font-size:{_tbl_hf};text-align:center;padding:2px 6px;}}
        .ect .sub {{background:#ecf0f1;color:#2c3e50;font-weight:600;font-size:{_tbl_hf};text-align:center;}}
        .ect .el {{background:#f0f4f8;color:#2c3e50;font-weight:600;font-size:{_tbl_lf};text-align:right;white-space:nowrap;border:1px solid #dde;width:{_tbl_lw};}}
        .ect .ev {{background:#eaf2fb;color:#2c3e50;font-weight:600;font-size:{_tbl_vf};text-align:center;border:1px solid #b8d4f0;width:{_tbl_vw};}}
        </style>
        <table class="ect">
            <tr><td class="sh" colspan="2">TOTAL RHS</td><td class="sh" colspan="2">FUEL CONSUMPTION</td></tr>
            <tr><td class="sub">DEVICE</td><td class="sub">RHS</td><td class="sub ev-hfo">HFO</td><td class="sub ev-do">DO</td></tr>
            {_sec1_rows}
        </table>
        <table class="ect">
            <tr><td class="sh" colspan="2">M/E PARAM</td><td class="sh" colspan="2">OIL CONSUMPTION</td></tr>
            {_sec2_rows}
        </table>
        <table class="ect">
            <tr><td class="sh" colspan="2">FUEL ROB</td><td class="sh" colspan="2">OIL ROB</td></tr>
            {_sec3_rows}
        </table>
        '''
        st.markdown(_output_html, unsafe_allow_html=True)

        # Dummy submit button (hidden — form requires one)
        st.form_submit_button("_", disabled=True, type="secondary")

# ---- EVENT CARD INPUT (editable fields) ----
with _eci_col:
    with st.form(f"event_input_form{_key_suffix}"):
        st.markdown('<div class="eci-marker"></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="card-header-right">{_eci_title}</div>', unsafe_allow_html=True)
        st.markdown('<table class="ect"><tr><td class="sh" colspan="4">CORRECTED CONSUMPTION</td></tr></table>', unsafe_allow_html=True)
        _corr_vals = {}
        _corr_rows = [
            ('HFO', 'me_hfo_cor_cons', 'M/E SYS', 'me_sys_cor_cons'),
            ('DO', 'me_do_cor_cons', 'M/E CYL', 'me_cyl_cor_cons'),
            ('', None, 'D/G SYS', 'dg_sys_cor_cons'),
        ]
        _lbl_fuel_cls = {'HFO': 'ec-lbl ec-lbl-hfo', 'DO': 'ec-lbl ec-lbl-do'}
        _lbl_oil_labels = {'M/E SYS', 'M/E CYL', 'D/G SYS'}
        for _i, (_l1, _k1, _l2, _k2) in enumerate(_corr_rows):
            _lbl1_cls = _lbl_fuel_cls.get(_l1, 'ec-lbl')
            _lbl2_cls = 'ec-lbl ec-lbl-oil' if _l2 in _lbl_oil_labels else 'ec-lbl'
            _c1, _c2, _c3, _c4 = st.columns([1.25, 1, 1.25, 1], gap='small')
            with _c1:
                st.markdown(f'<div class="{_lbl1_cls}">{_l1 if _l1 else "&nbsp;"}</div>', unsafe_allow_html=True)
            with _c2:
                if _k1:
                    _corr_vals[_k1] = st.text_input(
                        _k1,
                        value=str(c2_def.get(_k1, '')),
                        key=f'c2_corr_{_k1}_{_i}{_key_suffix}',
                        label_visibility='collapsed'
                    )
                else:
                    st.markdown('<div class="ec-out empty">&nbsp;</div>', unsafe_allow_html=True)
            with _c3:
                st.markdown(f'<div class="{_lbl2_cls}">{_l2}</div>', unsafe_allow_html=True)
            with _c4:
                _corr_vals[_k2] = st.text_input(
                    _k2,
                    value=str(c2_def.get(_k2, '')),
                    key=f'c2_corr_{_k2}_{_i}{_key_suffix}',
                    label_visibility='collapsed'
                )

        st.markdown('<table class="ect"><tr><td class="sh" colspan="2">FUEL SET</td><td class="sh" colspan="2">BUNKERED</td></tr></table>', unsafe_allow_html=True)
        _fuel_vals = {}
        _scrubber_rt = _ev.get('scrubber_rt', '--') if isinstance(_ev, dict) else '--'
        _fuel_rows = [
            ('ME_FO_set', 'me_fo_set', 'HFO', 'hfo_bnkr'),
            ('DG_FO_set', 'dg_fo_set', 'DO', 'do_bnkr'),
            ('BLR_FO_set', 'blr_fo_set', 'M/E SYS', 'me_sys_bnkr'),
            ('SCRUBBER RT', None, 'M/E CYL', 'me_cyl_bnkr'),
            ('', None, 'D/G SYS', 'dg_sys_bnkr'),
        ]
        _bunkered_lbl_cls = {'HFO': 'ec-lbl ec-lbl-hfo', 'DO': 'ec-lbl ec-lbl-do'}
        for _i, (_l1, _k1, _l2, _k2) in enumerate(_fuel_rows):
            _lbl2_cls = _bunkered_lbl_cls.get(_l2, 'ec-lbl ec-lbl-oil' if _l2 in _lbl_oil_labels else 'ec-lbl')
            _c1, _c2, _c3, _c4 = st.columns([1.25, 1, 1.25, 1], gap='small')
            with _c1:
                st.markdown(f'<div class="ec-lbl">{_l1 if _l1 else "&nbsp;"}</div>', unsafe_allow_html=True)
            with _c2:
                if _k1:
                    _fuel_vals[_k1] = st.text_input(
                        _k1,
                        value=str(c2_def.get(_k1, '')),
                        key=f'c2_fuel_{_k1}_{_i}{_key_suffix}',
                        label_visibility='collapsed'
                    )
                elif _l1 == 'SCRUBBER RT':
                    st.markdown(f'<div class="ec-out">{_scrubber_rt}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="ec-out empty">&nbsp;</div>', unsafe_allow_html=True)
            with _c3:
                st.markdown(f'<div class="{_lbl2_cls}">{_l2}</div>', unsafe_allow_html=True)
            with _c4:
                _fuel_vals[_k2] = st.text_input(
                    _k2,
                    value=str(c2_def.get(_k2, '')),
                    key=f'c2_fuel_{_k2}_{_i}{_key_suffix}',
                    label_visibility='collapsed'
                )

        c2_submitted = st.form_submit_button("SAVE EVENT CARD", type="primary", use_container_width=True)

    # Event Card save handler
    if c2_submitted and _eid and _eid > 1:
        # DEBUG: log raw _fuel_vals to file
        import json as _dbg_json
        _dbg_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'forobs_debug.log')
        with open(_dbg_log_path, 'a') as _df:
            _df.write(f"\n=== SAVE EVENT CARD for ID {_eid} ===\n")
            _df.write(f"_fuel_vals = {_dbg_json.dumps({k: repr(v) for k,v in _fuel_vals.items()})}\n")
            _df.write(f"_corr_vals = {_dbg_json.dumps({k: repr(v) for k,v in _corr_vals.items()})}\n")
        c2_data = {
            'me_fo_set':        str(_fuel_vals.get('me_fo_set', 'HFO')),
            'dg_fo_set':        str(_fuel_vals.get('dg_fo_set', 'HFO')),
            'blr_fo_set':       str(_fuel_vals.get('blr_fo_set', 'HFO')),
            'me_sys_calc_cons': safe_float(c2_def.get('me_sys_calc_cons', 0)),
            'dg_sys_calc_cons': safe_float(c2_def.get('dg_sys_calc_cons', 0)),
            'me_sys_cor_cons':  safe_float(_corr_vals.get('me_sys_cor_cons', 0)),
            'me_cyl_cor_cons':  safe_float(_corr_vals.get('me_cyl_cor_cons', 0)),
            'dg_sys_cor_cons':  safe_float(_corr_vals.get('dg_sys_cor_cons', 0)),
            'me_hfo_cor_cons':  safe_float(_corr_vals.get('me_hfo_cor_cons', 0)),
            'me_do_cor_cons':   safe_float(_corr_vals.get('me_do_cor_cons', 0)),
            'hfo_bnkr':         safe_float(_fuel_vals.get('hfo_bnkr', 0)),
            'do_bnkr':          safe_float(_fuel_vals.get('do_bnkr', 0)),
            'me_sys_bnkr':      safe_float(_fuel_vals.get('me_sys_bnkr', 0)),
            'me_cyl_bnkr':      safe_float(_fuel_vals.get('me_cyl_bnkr', 0)),
            'dg_sys_bnkr':      safe_float(_fuel_vals.get('dg_sys_bnkr', 0)),
        }
        # DEBUG: log c2_data
        with open(_dbg_log_path, 'a') as _df:
            _df.write(f"c2_data = {_dbg_json.dumps({k: repr(v) for k,v in c2_data.items()})}\n")
        update_event(_eid, c2_data)
        with st.spinner(f"Recalculating chain from ID {_eid}…"):
            recalculate_chain(_eid)
        try:
            rebuild_chart_data()
        except Exception:
            pass
        # DEBUG: verify DB after save
        with open(_dbg_log_path, 'a') as _df:
            _dbg_conn = get_connection()
            _dbg_row = _dbg_conn.execute(f"SELECT hfo_bnkr, do_bnkr, me_sys_bnkr FROM events WHERE id = {_eid}").fetchone()
            _df.write(f"DB after save: hfo_bnkr={_dbg_row[0]}, do_bnkr={_dbg_row[1]}, me_sys_bnkr={_dbg_row[2]}\n")
            _dbg_conn.close()
        st.success(f"Event Card saved for Event #{_eid}!")
        st.rerun()

# ---- RIGHT COLUMN: INPUT CARD ----
_card_title = f"INPUT CARD  ID_{st.session_state.editing_id}" if st.session_state.editing_id else "INPUT CARD  (new)"

with _inp_col:
    with st.form(f"input_card_form{_key_suffix}"):
        st.markdown(f'<div class="card-header-right">{_card_title}</div>', unsafe_allow_html=True)

        # Inject DEP lock data for JavaScript
        _dep_active_js = '1' if _dep_active else '0'
        _dep_me_rev = str(_dep_prev_vals.get('me_rev_c') or '')
        _dep_main_fm = str(_dep_prev_vals.get('main_flmtr') or '')
        _dep_cyl_oil = str(_dep_prev_vals.get('cyl_oil_count') or '')
        _dep_me_pwr = str(_dep_prev_vals.get('me_pwrmtr') or '')
        _dep_me_hrs = str(_dep_prev_vals.get('me_hrs') or '')
        st.markdown(
            f'<div class="dep-lock-data" data-dep-active="{_dep_active_js}"'
            f' data-me-rev-c="{_dep_me_rev}" data-main-flmtr="{_dep_main_fm}"'
            f' data-cyl-oil-count="{_dep_cyl_oil}" data-me-pwrmtr="{_dep_me_pwr}"'
            f' data-me-hrs="{_dep_me_hrs}" style="display:none"></div>',
            unsafe_allow_html=True
        )

        row1_fields = [
            ("DATE",          "inp_date",     defaults['date']),
            ("TIME",          "inp_time",     str(defaults['time'])),
            ("EVENT",         "inp_event",    str(defaults['event'])),
            ("PLACE",         "inp_place",    str(defaults['place'])),
            ("ME REV C",      "inp_me_rev",   str(defaults['me_rev_c'])),
            ("MAIN FLMTR",    "inp_main_fm",  str(defaults['main_flmtr'])),
            ("DG IN FLMTR",   "inp_dg_in",    str(defaults['dg_in_flmtr'])),
            ("DG OUT FLMTR",  "inp_dg_out",   str(defaults['dg_out_flmtr'])),
            ("BLR FLMTR",     "inp_blr_fm",   str(defaults['blr_flmtr'])),
            ("CYL OIL COUNT", "inp_cyl_oil",  str(defaults['cyl_oil_count'])),
            ("ME PWRMTR",     "inp_me_pwr",   str(defaults['me_pwrmtr'])),
            ("M/E HRS",       "inp_me_hrs",   str(defaults['me_hrs'])),
            ("D/G 1 HRS",     "inp_dg1_hrs",  str(defaults['dg1_hrs'])),
            ("D/G 2 HRS",     "inp_dg2_hrs",  str(defaults['dg2_hrs'])),
            ("D/G 3 HRS",     "inp_dg3_hrs",  str(defaults['dg3_hrs'])),
            ("BOILER HRS",    "inp_blr_hrs",  str(defaults['boiler_hrs'])),
            ("D/G1 MWh",      "inp_dg1_mwh",  str(defaults['dg1_mwh'])),
            ("D/G2 MWh",      "inp_dg2_mwh",  str(defaults['dg2_mwh'])),
            ("D/G3 MWh",      "inp_dg3_mwh",  str(defaults['dg3_mwh'])),
            ("SOx/CO2",       "inp_sox",      str(defaults['sox_co2'])),
        ]

        row2_fields = [
            ("OCL PP A",  "inp_ocl_a",   str(defaults['ocl_pp_a'])),
            ("OCL PP B",  "inp_ocl_b",   str(defaults['ocl_pp_b'])),
            ("OCL PP C",  "inp_ocl_c",   str(defaults['ocl_pp_c'])),
            ("PHE A",     "inp_phe_a",   str(defaults['phe_a'])),
            ("PHE B",     "inp_phe_b",   str(defaults['phe_b'])),
            ("SEA TEMP",  "inp_sea_temp",str(defaults['sea_temp'])),
            ("ST LO TMP", "inp_st_lo",   str(defaults['st_lo_tmp'])),
            ("WCU SEP",   "inp_wcu",     str(defaults['wcu_sep'])),
            ("COMP 1",    "inp_comp1",   str(defaults['comp_1'])),
            ("COMP 2",    "inp_comp2",   str(defaults['comp_2'])),
            ("W. COMP",   "inp_wcomp",   str(defaults['w_comp'])),
        ]

        inputs = {}
        # Pre-populate row2 field keys with empty defaults (right side is MID-only;
        # if not rendered the save handler still needs these keys in the dict)
        for _, _r2k, _ in row2_fields:
            inputs[_r2k] = ''

        for i in range(20):
            c1, c2, c3, c4 = st.columns([1.2, 1, 1.2, 1])

            r1_label, r1_key, r1_val = row1_fields[i]
            with c1:
                st.markdown(f'<div class="card-label">{r1_label}</div>', unsafe_allow_html=True)
            with c2:
                if r1_label == "EVENT":
                    inputs[r1_key] = st.selectbox(
                        r1_label, EVENT_TYPES,
                        index=EVENT_TYPES.index(r1_val) if r1_val in EVENT_TYPES else 0,
                        key=r1_key + _key_suffix, label_visibility="collapsed"
                    )
                elif r1_label == "DATE":
                    inputs[r1_key] = st.date_input(r1_label, value=r1_val, format="DD/MM/YYYY", key=r1_key + _key_suffix, label_visibility="collapsed")
                else:
                    inputs[r1_key] = st.text_input(r1_label, value=r1_val, key=r1_key + _key_suffix, label_visibility="collapsed")

            if i < len(row2_fields):
                r2_label, r2_key, r2_val = row2_fields[i]
                if not row2_disabled:
                    # MID event: show right-side fields normally
                    with c3:
                        st.markdown(f'<div class="card-row2-label">{r2_label}</div>', unsafe_allow_html=True)
                    with c4:
                        inputs[r2_key] = st.text_input(r2_label, value=r2_val, key=r2_key + _key_suffix, label_visibility="collapsed")
                # else: right side reserved for MID events only — leave c3/c4 empty
            elif i == 19:
                with c3:
                    submitted = st.form_submit_button("SAVE", type="primary", use_container_width=True)
                with c4:
                    delete_clicked = st.form_submit_button("DEL", use_container_width=True)

    # ---- INPUT CARD: SAVE / DELETE handlers (inside right column) ----
    if submitted:
        import re as _re
        errors = []

        row1_required = {
            'TIME': inputs['inp_time'],
            'EVENT': inputs['inp_event'], 'PLACE': inputs['inp_place'],
        }
        missing_r1 = [k for k, v in row1_required.items() if not str(v).strip()]
        if missing_r1:
            errors.append(f"Required: {', '.join(missing_r1)}")

        time_val = _fmt_time(inputs['inp_time'])
        if time_val:
            m = _re.match(r'^(\d{2}):(\d{2})$', time_val)
            if not m:
                errors.append("TIME must be HH:MM or HHMM (e.g. 1234 or 12:34)")
            else:
                hh, mm = int(m.group(1)), int(m.group(2))
                if hh > 23:
                    errors.append("TIME hours must be 00-23")
                if mm > 59:
                    errors.append("TIME minutes must be 00-59")

        int_field_map = [
            ('inp_me_rev', 'ME REV C'),
            ('inp_cyl_oil', 'CYL OIL COUNT'),
        ]
        for fkey, flabel in int_field_map:
            val = str(inputs[fkey]).strip()
            if val:
                if not _re.match(r'^\d+$', val):
                    errors.append(f"{flabel}: whole number only (e.g. 123, 6351)")

        flowmeter_field_map = [
            ('inp_main_fm', 'MAIN FLMTR'),
            ('inp_dg_in', 'DG IN FLMTR'),
            ('inp_dg_out', 'DG OUT FLMTR'),
            ('inp_blr_fm', 'BLR FLMTR'),
        ]
        for fkey, flabel in flowmeter_field_map:
            val = str(inputs[fkey]).strip()
            if val and not _re.match(r'^\d+(?:[\.,]\d+)?$', val):
                errors.append(f"{flabel}: number format (e.g. 123, 123.4, 123,4)")

        hrs_field_map = [
            ('inp_me_hrs', 'M/E HRS'), ('inp_dg1_hrs', 'D/G 1 HRS'),
            ('inp_dg2_hrs', 'D/G 2 HRS'), ('inp_dg3_hrs', 'D/G 3 HRS'),
            ('inp_blr_hrs', 'BOILER HRS'),
        ]
        for fkey, flabel in hrs_field_map:
            val = str(inputs[fkey]).strip().replace(',', '.')
            if val:
                if _re.match(r'^\d+$', val):
                    inputs[fkey] = val + '.00'
                elif _re.match(r'^\d+\.\d+$', val):
                    inputs[fkey] = val  # normalise comma→dot
                else:
                    errors.append(f"{flabel}: decimal format required (e.g. 12.2, 123.56, 91.90) or whole number")

        is_mid = inputs.get('inp_event', 'NOON') == "MID"
        row2_off = not is_mid

        if is_mid:
            row2_keys = ['inp_ocl_a','inp_ocl_b','inp_ocl_c','inp_phe_a','inp_phe_b',
                         'inp_sea_temp','inp_st_lo','inp_wcu','inp_comp1','inp_comp2','inp_wcomp']
            row2_labels = ['OCL PP A','OCL PP B','OCL PP C','PHE A','PHE B',
                           'SEA TEMP','ST LO TMP','WCU SEP','COMP 1','COMP 2','W. COMP']
            missing_r2 = [lbl for lbl, k in zip(row2_labels, row2_keys) if not str(inputs[k]).strip()]
            if missing_r2:
                errors.append(f"MID event requires Row 2: {', '.join(missing_r2)}")
            row2_hrs_map = [
                ('inp_ocl_a', 'OCL PP A'), ('inp_ocl_b', 'OCL PP B'), ('inp_ocl_c', 'OCL PP C'),
                ('inp_phe_a', 'PHE A'), ('inp_phe_b', 'PHE B'),
                ('inp_wcu', 'WCU SEP'), ('inp_comp1', 'COMP 1'), ('inp_comp2', 'COMP 2'), ('inp_wcomp', 'W. COMP'),
            ]
            for fkey, flabel in row2_hrs_map:
                val = str(inputs[fkey]).strip()
                if val:
                    if _re.match(r'^\d+$', val):
                        inputs[fkey] = val + '.00'
                    elif not _re.match(r'^\d+\.\d{2}$', val):
                        errors.append(f"{flabel}: format XX.XX (e.g. 123.06) or whole number")
            temp_field_map = [('inp_sea_temp', 'SEA TEMP'), ('inp_st_lo', 'ST LO TMP')]
            for fkey, flabel in temp_field_map:
                val = str(inputs[fkey]).strip()
                if val:
                    if _re.match(r'^\d+$', val):
                        inputs[fkey] = val + '.0'
                    elif not _re.match(r'^\d+\.\d$', val):
                        errors.append(f"{flabel}: temperature format XX.X (e.g. 12.3, 11.7)")

        if errors:
            for e in errors:
                st.error(e)
        else:
            _date_for_db = inputs['inp_date'].strftime('%d-%m-%y') if hasattr(inputs['inp_date'], 'strftime') else str(inputs['inp_date'])
            event_data = {
                'date': _date_for_db, 'time': time_val,
                'event': inputs['inp_event'], 'place': inputs['inp_place'],
                'me_rev_c': safe_int(inputs['inp_me_rev']),
                'main_flmtr': safe_float(inputs['inp_main_fm']),
                'dg_in_flmtr': safe_float(inputs['inp_dg_in']),
                'dg_out_flmtr': safe_float(inputs['inp_dg_out']),
                'blr_flmtr': safe_float(inputs['inp_blr_fm']),
                'cyl_oil_count': safe_int(inputs['inp_cyl_oil']),
                'me_pwrmtr': safe_float(inputs['inp_me_pwr']),
                'me_hrs': safe_float(inputs['inp_me_hrs']),
                'dg1_hrs': safe_float(inputs['inp_dg1_hrs']),
                'dg2_hrs': safe_float(inputs['inp_dg2_hrs']),
                'dg3_hrs': safe_float(inputs['inp_dg3_hrs']),
                'boiler_hrs': safe_float(inputs['inp_blr_hrs']),
                'dg1_mwh': safe_float(inputs['inp_dg1_mwh']),
                'dg2_mwh': safe_float(inputs['inp_dg2_mwh']),
                'dg3_mwh': safe_float(inputs['inp_dg3_mwh']),
                'sox_co2': safe_float(inputs['inp_sox']),
                'ocl_pp_a': safe_float(inputs['inp_ocl_a']) if not row2_off else None,
                'ocl_pp_b': safe_float(inputs['inp_ocl_b']) if not row2_off else None,
                'ocl_pp_c': safe_float(inputs['inp_ocl_c']) if not row2_off else None,
                'phe_a': safe_float(inputs['inp_phe_a']) if not row2_off else None,
                'phe_b': safe_float(inputs['inp_phe_b']) if not row2_off else None,
                'sea_temp': safe_float(inputs['inp_sea_temp']) if not row2_off else None,
                'st_lo_tmp': safe_float(inputs['inp_st_lo']) if not row2_off else None,
                'wcu_sep': safe_float(inputs['inp_wcu']) if not row2_off else None,
                'comp_1': safe_float(inputs['inp_comp1']) if not row2_off else None,
                'comp_2': safe_float(inputs['inp_comp2']) if not row2_off else None,
                'w_comp': safe_float(inputs['inp_wcomp']) if not row2_off else None,
            }
            # ── DEP M/E counter lock enforcement (server-side) ──
            if (inputs['inp_event'] == 'DEPARTURE'
                    and _app_settings_now.get('dep_stops_me_counters', 'no') == 'yes'):
                _sav_prev = _get_prev_event_for_dep(st.session_state.editing_id)
                if _sav_prev:
                    event_data['me_rev_c'] = safe_int(fmt_field('me_rev_c', _sav_prev.get('me_rev_c')))
                    event_data['main_flmtr'] = safe_float(fmt_field('main_flmtr', _sav_prev.get('main_flmtr')))
                    event_data['cyl_oil_count'] = safe_int(fmt_field('cyl_oil_count', _sav_prev.get('cyl_oil_count')))
                    event_data['me_pwrmtr'] = safe_float(fmt_field('me_pwrmtr', _sav_prev.get('me_pwrmtr')))
                    event_data['me_hrs'] = safe_float(fmt_field('me_hrs', _sav_prev.get('me_hrs')))
            if st.session_state.editing_id:
                update_event(st.session_state.editing_id, event_data)
                with st.spinner(f"Recalculating chain from ID {st.session_state.editing_id}…"):
                    recalculate_chain(st.session_state.editing_id)
                try:
                    rebuild_chart_data()
                except Exception:
                    pass
                st.success(f"Event #{st.session_state.editing_id} updated!")
            else:
                insert_event(event_data)
                conn_tmp = get_connection()
                new_id = conn_tmp.execute("SELECT MAX(id) FROM events").fetchone()[0]
                conn_tmp.close()
                if new_id and new_id > 1:
                    calculate_event(new_id)
                try:
                    rebuild_chart_data()
                except Exception:
                    pass
                st.success("New event saved!")
            st.session_state.editing_id = None
            st.session_state.new_entry_mode = False
            st.rerun()

    if delete_clicked:
        if st.session_state.editing_id:
            st.session_state.confirm_delete = True
        else:
            st.toast("No event selected to delete. Click an event ID in the logbook first.", icon="⚠️")

# ---- DELETE CONFIRMATION DIALOG ----
@st.dialog("Confirm Delete")
def _confirm_delete_dialog():
    _del_id = st.session_state.editing_id
    st.warning(f"Are you sure you want to DELETE Event #{_del_id}?")
    _dc1, _dc2 = st.columns(2)
    with _dc1:
        if st.button("YES — Delete", type="primary", use_container_width=True):
            delete_event(_del_id)
            recalculate_chain(_del_id)
            try:
                rebuild_chart_data()
            except Exception:
                pass
            st.session_state.editing_id = None
            st.session_state.confirm_delete = False
            st.rerun()
    with _dc2:
        if st.button("NO — Cancel", use_container_width=True):
            st.session_state.confirm_delete = False
            st.rerun()

if st.session_state.confirm_delete and st.session_state.editing_id:
    _confirm_delete_dialog()

# ---- FUNCTIONS PANEL (floating card, includes settings) ----
_app_settings_now = _load_app_settings()
with _func_col:
    with st.form("functions_panel_form"):
        st.markdown('<div class="card-header-right">FUNCTIONS PANEL</div>', unsafe_allow_html=True)
        _fp_ok, _fp_url = _ensure_elcalc_server()
        _fp_btn_style = (
            "display:block;width:100%;text-align:center;padding:6px 12px;"
            "background:#0e1117;color:white;border-radius:6px;text-decoration:none;"
            "font-size:14px;font-weight:400;border:1px solid rgba(250,250,250,0.2);"
            "cursor:pointer;margin-bottom:6px;"
        )
        if _fp_ok:
            st.markdown(
                f'<a href="{_fp_url}" target="_blank" style="{_fp_btn_style}">⛽ Fuel plan</a>',
                unsafe_allow_html=True
            )
        else:
            _fp_dis_style = _fp_btn_style + "opacity:0.4;cursor:not-allowed;"
            st.markdown(
                f'<div style="{_fp_dis_style}">⛽ Fuel plan (unavailable)</div>',
                unsafe_allow_html=True
            )
            st.caption("Fuel plan unavailable (missing elcalc folder or local port blocked)")

        st.markdown(
            '<div style="border-top:1px solid #dde;margin:6px 0 4px 0;'
            'font-size:12px;font-weight:700;color:#2c3e50;padding-top:5px;">⚙ SETTINGS</div>',
            unsafe_allow_html=True
        )

        st.markdown('<div style="font-size:12px;font-weight:600;color:#2c3e50;margin:4px 0 2px 0;">Does DEP stop M/E counters?</div>', unsafe_allow_html=True)
        _dep_idx = 0 if _app_settings_now.get('dep_stops_me_counters', 'no') == 'yes' else 1
        _dep_choice = st.radio(
            "dep_me_counters",
            ["Yes", "No"],
            index=_dep_idx,
            horizontal=True,
            label_visibility="collapsed",
            key="sett_dep_radio"
        )

        st.markdown('<div style="font-size:12px;font-weight:600;color:#2c3e50;margin:6px 0 2px 0;">Boiler fuel consumption</div>', unsafe_allow_html=True)
        _blr_idx = 1 if _app_settings_now.get('boiler_fuel_mode', 'flowmeter') == 'user_defined' else 0
        _blr_choice = st.radio(
            "boiler_mode",
            ["Flowmeter", "User Defined [mt/h]"],
            index=_blr_idx,
            horizontal=True,
            label_visibility="collapsed",
            key="sett_blr_radio"
        )
        _blr_rate_val = float(_app_settings_now.get('boiler_user_defined_rate') or 0.0)
        _blr_rate = st.number_input(
            "Rate [mt/h]:",
            value=_blr_rate_val,
            min_value=0.0,
            step=0.0001,
            format="%.4f",
            key="sett_blr_rate"
        )

        _save_settings = st.form_submit_button("SAVE SETTINGS", type="primary", use_container_width=True)

    if _save_settings:
        _new_settings = {
            'dep_stops_me_counters': 'yes' if _dep_choice == 'Yes' else 'no',
            'boiler_fuel_mode': 'user_defined' if 'User Defined' in _blr_choice else 'flowmeter',
            'boiler_user_defined_rate': float(_blr_rate),
        }
        if not _save_app_settings(_new_settings):
            st.toast("Failed to save settings (check file permissions).", icon="❌")
        else:
            st.session_state['_settings_saved_toast'] = True
            st.rerun()

# Show settings-saved toast after rerun (so it appears on the fresh render)
if st.session_state.pop('_settings_saved_toast', False):
    st.toast("Settings saved!", icon="✅")

# ============ LEFT BAR (Sidebar) - Events Logbook ============
with st.sidebar:
    events_df = fetch_all_events_stable()
    _total_log_count = len(events_df) if not events_df.empty else 0
    st.markdown(f'<div style="font-size:14px;font-weight:700;color:#2c3e50;padding:0 0 2px 0;margin:-1rem 0 0 0;">\U0001F4D6 Event Logbook ({_total_log_count} ID\'s)</div>', unsafe_allow_html=True)
    
    if not events_df.empty:
        col_rename = {c: c.upper() for c in events_df.columns}
        display_df = events_df.rename(columns=col_rename)

        if '_logbook_selected_columns' not in st.session_state:
            st.session_state['_logbook_selected_columns'] = list(display_df.columns)
        if '_logbook_pending_columns' not in st.session_state:
            st.session_state['_logbook_pending_columns'] = list(st.session_state['_logbook_selected_columns'])
        if '_logbook_pinned_columns' not in st.session_state:
            _pin_defaults = ['ID', 'DATE', 'TIME', 'EVENT', 'PLACE', 'ST_TIME']
            st.session_state['_logbook_pinned_columns'] = [c for c in _pin_defaults if c in display_df.columns]
        if '_logbook_pending_pins' not in st.session_state:
            st.session_state['_logbook_pending_pins'] = list(st.session_state['_logbook_pinned_columns'])

        if 'ID' not in st.session_state['_logbook_selected_columns']:
            st.session_state['_logbook_selected_columns'] = ['ID'] + [
                c for c in st.session_state['_logbook_selected_columns'] if c != 'ID'
            ]
        if 'ID' not in st.session_state['_logbook_pending_columns']:
            st.session_state['_logbook_pending_columns'] = ['ID'] + [
                c for c in st.session_state['_logbook_pending_columns'] if c != 'ID'
            ]

        selected_cols = [
            c for c in st.session_state['_logbook_selected_columns']
            if c in display_df.columns
        ]
        if 'ID' not in selected_cols:
            selected_cols = ['ID'] + selected_cols
        if not selected_cols:
            selected_cols = ['ID']

        table_df = display_df[selected_cols].copy()
        total_rows = len(table_df)

        # Fixed window of 51 rows, FIND navigates
        window_size = 51
        max_start = max(0, total_rows - window_size)
        if '_lb_start' not in st.session_state:
            st.session_state['_lb_start'] = 0
        if st.session_state['_lb_start'] > max_start:
            st.session_state['_lb_start'] = max_start
        if st.session_state['_lb_start'] < 0:
            st.session_state['_lb_start'] = 0

        # ── Controls row: New Entry | Columns | Find ──
        _sb_c1, _sb_c2, _sb_c3, _sb_c4 = st.columns([0.8, 0.8, 2.4, 0.5])
        with _sb_c1:
            if st.button("\u2795", use_container_width=True, type="secondary"):
                st.session_state.editing_id = None
                st.session_state.new_entry_mode = True
                st.session_state.confirm_delete = False
                st.rerun()
        with _sb_c2:
            with st.popover("\U0001F4CB", use_container_width=True):
                st.caption("Select columns to load in logbook view")
                pending = st.multiselect(
                    "Columns",
                    options=list(display_df.columns),
                    default=[c for c in st.session_state['_logbook_pending_columns'] if c in display_df.columns],
                    key="_logbook_pending_columns_widget",
                )
                if 'ID' not in pending:
                    pending = ['ID'] + pending
                st.caption("Pinned columns (stable)")
                pending_pins = st.multiselect(
                    "Pinned",
                    options=pending,
                    default=[c for c in st.session_state['_logbook_pending_pins'] if c in pending],
                    key="_logbook_pending_pins_widget",
                )
                if 'ID' not in pending_pins:
                    pending_pins = ['ID'] + pending_pins
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("OK", use_container_width=True, key="_logbook_cols_ok"):
                        st.session_state['_logbook_selected_columns'] = pending
                        st.session_state['_logbook_pending_columns'] = pending
                        st.session_state['_logbook_pinned_columns'] = pending_pins
                        st.session_state['_logbook_pending_pins'] = pending_pins
                        st.rerun()
                with cc2:
                    if st.button("CANCEL", use_container_width=True, key="_logbook_cols_cancel"):
                        st.session_state['_logbook_pending_columns'] = list(st.session_state['_logbook_selected_columns'])
                        st.session_state['_logbook_pending_pins'] = list(st.session_state['_logbook_pinned_columns'])
                        st.rerun()
        with _sb_c3:
            _find_val = st.text_input("ID or Date", key="_lb_find_val", placeholder="ID or dd/mm/yyyy", label_visibility="collapsed")
        with _sb_c4:
            _find_clicked = st.button("\U0001F50D", use_container_width=True, key="_lb_find_btn")

        # ── FIND processing ──
        if _find_clicked and _find_val and _find_val.strip():
            import re as _re
            _fv = _find_val.strip()
            _found_pos = None
            if _fv.isdigit():
                _target_id = int(_fv)
                _id_vals = table_df['ID'].values
                _positions = [i for i, v in enumerate(_id_vals) if int(v) == _target_id]
                if _positions:
                    _found_pos = _positions[0]
            else:
                _date_match = _re.match(r'^(\d{1,2})[/\-.](\d{1,2})[/\-.](.+)$', _fv)
                if _date_match and 'DATE' in table_df.columns:
                    _dd, _mm, _yy = _date_match.groups()
                    if len(_yy) == 4:
                        _yy = _yy[2:]
                    _db_date = f"{_dd.zfill(2)}-{_mm.zfill(2)}-{_yy.zfill(2)}"
                    _date_vals = table_df['DATE'].values.astype(str)
                    _positions = [i for i, v in enumerate(_date_vals) if v.strip() == _db_date]
                    if _positions:
                        _found_pos = (_positions[0] + _positions[-1]) // 2
            if _found_pos is not None:
                _new_start = _found_pos - 25
                _new_start = max(0, min(_new_start, max_start))
                st.session_state['_lb_start'] = _new_start
                st.rerun()

        start_idx = int(st.session_state['_lb_start'])
        end_idx = min(total_rows, start_idx + window_size)
        window_df = table_df.iloc[start_idx:end_idx].copy()
        
        yellow_base_cols = ['DATE', 'TIME', 'PLACE']
        green_hrs_cols = ['ME_HRS', 'DG1_HRS', 'DG2_HRS', 'DG3_HRS', 'BOILER_HRS',
                          'OCL_PP_A', 'OCL_PP_B', 'OCL_PP_C', 'PHE_A', 'PHE_B',
                          'WCU_SEP', 'COMP_1', 'COMP_2', 'W_COMP']
        green_event_cols = ['EVENT']
        orange_cols = ['ME_REV_C', 'MAIN_FLMTR', 'DG_IN_FLMTR', 'DG_OUT_FLMTR', 'BLR_FLMTR', 'CYL_OIL_COUNT', 'ME_PWRMTR']
        blue_cols = ['DG1_MWH', 'DG2_MWH', 'DG3_MWH']
        gray_cols = ['SEA_TEMP', 'ST_LO_TMP']
        red_cols = ['SOX_CO2']
        calc_time_cols = ['ST_TIME', 'ME_DIFF', 'DG1_DIFF', 'DG2_DIFF', 'DG3_DIFF', 'BLR_DIFF']
        calc_perf_cols = ['AVG_PWR', 'AVG_RPM', 'TTL_PWR', 'TTL_RPM']
        oil_rob_cols = ['ME_SYS_ROB', 'ME_CYL_ROB', 'DG_SYS_ROB']
        fuel_rob_cols = ['HFO_ROB', 'DO_ROB']
        oil_cons_cols = ['ME_SYS_CALC_CONS', 'ME_CYL_CALC_CONS', 'DG_SYS_CALC_CONS',
                         'ME_SYS_ACC_CONS', 'ME_CYL_ACC_CONS', 'DG_SYS_ACC_CONS']
        fuel_cons_cols = ['ME_HFO_CALC_CONS', 'ME_DO_CALC_CONS', 'DG_HFO_CALC_CONS', 'DG_DO_CALC_CONS',
                          'BLR_HFO_CALC_CONS', 'BLR_DO_CALC_CONS',
                          'ME_HFO_ACC_CONS', 'ME_DO_ACC_CONS', 'DG_HFO_ACC_CONS', 'DG_DO_ACC_CONS',
                          'BLR_HFO_ACC_CONS', 'BLR_DO_ACC_CONS']
        fo_set_cols = ['ME_FO_SET', 'DG_FO_SET', 'BLR_FO_SET']
        cor_cols = ['ME_SYS_COR_CONS', 'ME_CYL_COR_CONS', 'DG_SYS_COR_CONS',
                    'ME_HFO_COR_CONS', 'ME_DO_COR_CONS', 'DG_HFO_COR_CONS', 'DG_DO_COR_CONS',
                    'BLR_HFO_COR_CONS', 'BLR_DO_COR_CONS']
        
        def color_columns(col):
            if col.name in yellow_base_cols:
                return ['background-color: #fffde7'] * len(col)
            elif col.name in green_event_cols:
                return ['background-color: #e8f5e9'] * len(col)
            elif col.name in green_hrs_cols:
                return ['background-color: #e8f5e9'] * len(col)
            elif col.name in orange_cols:
                return ['background-color: #fff3e0'] * len(col)
            elif col.name in blue_cols:
                return ['background-color: #e3f2fd'] * len(col)
            elif col.name in gray_cols:
                return ['background-color: #f0f0f0'] * len(col)
            elif col.name in red_cols:
                return ['background-color: #ffebee'] * len(col)
            elif col.name in calc_time_cols:
                return ['background-color: #e0f7fa'] * len(col)
            elif col.name in calc_perf_cols:
                return ['background-color: #fce4ec'] * len(col)
            elif col.name in oil_rob_cols:
                return ['background-color: #fff9c4'] * len(col)
            elif col.name in fuel_rob_cols:
                return ['background-color: #fff9c4'] * len(col)
            elif col.name in oil_cons_cols or col.name in fuel_cons_cols:
                return ['background-color: #f3e5f5'] * len(col)
            elif col.name in cor_cols:
                return ['background-color: #fbe9e7'] * len(col)
            elif col.name in fo_set_cols:
                return ['background-color: #efebe9'] * len(col)
            return [''] * len(col)
        
        _pinned_cols = [
            c for c in st.session_state.get('_logbook_pinned_columns', ['ID', 'DATE', 'TIME', 'EVENT', 'PLACE', 'ST_TIME'])
            if c in window_df.columns
        ]
        if 'ID' not in _pinned_cols and 'ID' in window_df.columns:
            _pinned_cols = ['ID'] + _pinned_cols

        _unpinned_cols = [c for c in window_df.columns if c not in _pinned_cols]
        _ordered_cols = _pinned_cols + _unpinned_cols
        window_df = window_df[_ordered_cols]

        styled_df = window_df.style.apply(color_columns).format(
            {col: '{:.2f}' for col in window_df.select_dtypes(include='number').columns if col != 'ID'},
            na_rep=''
        )

        _col_cfg = {}
        for _col in window_df.columns:
            if _col == 'ID':
                _col_cfg[_col] = st.column_config.NumberColumn("ID", width=50, pinned=(_col in _pinned_cols))
            else:
                _col_cfg[_col] = st.column_config.TextColumn(_col, pinned=(_col in _pinned_cols))

        selection = st.dataframe(
            styled_df,
            hide_index=True,
            width='stretch',
            height=420,
            column_config=_col_cfg,
            on_select="rerun",
            selection_mode="single-row",
            key="events_table",
        )
        
        if selection and selection.selection and selection.selection.rows:
            selected_row_idx = selection.selection.rows[0]
            selected_event_id = int(window_df.iloc[selected_row_idx]['ID'])
            if st.session_state.editing_id != selected_event_id:
                st.session_state.editing_id = selected_event_id
                st.session_state.confirm_delete = False
                st.rerun()
        
        # (controls moved above dataframe)

        # ═══════════════════════════════════════════════════
        # ── EVENT CALCULATOR ──────────────────────────────
        # ═══════════════════════════════════════════════════
        st.markdown('<div style="font-size:13px;font-weight:700;color:#2c3e50;padding:4px 0 2px 0;margin:0;">\U0001F5A9 EVENT CALCULATOR</div>', unsafe_allow_html=True)

        st.markdown('<div style="background:#f4f7fa;border:1px solid #d0dbe6;border-radius:4px;padding:6px 6px 2px 6px;margin:0 0 4px 0;">', unsafe_allow_html=True)
        _ec_c1, _ec_c2 = st.columns(2)
        with _ec_c1:
            _ec_start_raw = st.text_input("EVENT START ID", value=str(st.session_state.get('_ec_start_id', 2)), key="_ec_start_id_w")
        with _ec_c2:
            _ec_end_raw = st.text_input("EVENT END ID", value=str(st.session_state.get('_ec_end_id', max(2, total_rows + 1))), key="_ec_end_id_w")
        st.markdown('</div>', unsafe_allow_html=True)
        try:
            _ec_start_id = max(2, int(_ec_start_raw))
        except (ValueError, TypeError):
            _ec_start_id = 2
        try:
            _ec_end_id = max(2, int(_ec_end_raw))
        except (ValueError, TypeError):
            _ec_end_id = max(2, total_rows + 1)
        st.session_state['_ec_start_id'] = _ec_start_id
        st.session_state['_ec_end_id'] = _ec_end_id

        # ── Compute calculator values ──────────────────────
        def _ec_fetch_event(eid):
            """Fetch a single event row as dict."""
            conn = None
            try:
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("SELECT * FROM events WHERE id = ?", (eid,))
                row = cur.fetchone()
                if row is None:
                    return None
                cols = [d[0] for d in cur.description]
                return dict(zip(cols, row))
            except Exception:
                return None
            finally:
                if conn:
                    conn.close()

        def _ec_fetch_range(sid, eid):
            """Fetch events from sid to eid inclusive, ordered by id."""
            conn = None
            try:
                conn = get_connection()
                df = pd.read_sql_query(
                    "SELECT * FROM events WHERE id >= ? AND id <= ? ORDER BY id",
                    conn, params=(sid, eid))
                return df
            except Exception:
                return pd.DataFrame()
            finally:
                if conn:
                    conn.close()

        def _ec_safe_float(v):
            try:
                f = float(v) if v is not None and v != '' and str(v) != 'None' else 0.0
                return f
            except (ValueError, TypeError):
                return 0.0

        def _ec_hhmm_to_min(v):
            if not v or v == 'None' or v == '00:00':
                return 0
            try:
                parts = str(v).split(':')
                return int(parts[0]) * 60 + (int(parts[1]) if len(parts) > 1 else 0)
            except (ValueError, IndexError):
                return 0

        def _ec_min_to_hhmm(total_min):
            total_min = max(0, int(total_min))
            return f"{total_min // 60:02d}:{total_min % 60:02d}"

        def _ec_parse_dt(row):
            try:
                _d = datetime.strptime(str(row.get('date', '') or ''), '%d-%m-%y')
            except Exception:
                return None
            try:
                _t = str(row.get('time', '00:00') or '00:00')
                _hh, _mm = _t.split(':')
                return _d.replace(hour=int(_hh), minute=int(_mm))
            except Exception:
                return _d

        def _ec_fmt(val, decimals=2):
            if val is None or val == 0 or val == 0.0:
                return '--'
            try:
                s = f"{float(val):.{decimals}f}".rstrip('0').rstrip('.')
                return s if s and s != '0' else '--'
            except (ValueError, TypeError):
                return '--'

        _ec_sid = st.session_state['_ec_start_id']
        _ec_eid = st.session_state['_ec_end_id']

        try:
          if _ec_sid >= 2 and _ec_eid >= _ec_sid:
            ev_start = _ec_fetch_event(_ec_sid)
            ev_end = _ec_fetch_event(_ec_eid)
            range_df = _ec_fetch_range(_ec_sid, _ec_eid)

            if ev_start and ev_end and not range_df.empty:
                # For runtime-based metrics, exclude the newest event in range.
                # Example: for 1→100, duration fields from ID 100 are not counted.
                calc_df = range_df.iloc[:-1].copy() if len(range_df) > 1 else range_df.iloc[0:0].copy()

                # ── TTL TIME (end datetime - start datetime) ──
                _st_dt = _ec_parse_dt(ev_start)
                _en_dt = _ec_parse_dt(ev_end)
                if _st_dt and _en_dt:
                    _ttl_min = max(0, int((_en_dt - _st_dt).total_seconds() / 60))
                else:
                    _ttl_min = sum(_ec_hhmm_to_min(r.get('st_time')) for _, r in calc_df.iterrows())
                _ttl_time_s = _ec_min_to_hhmm(_ttl_min)

                # ── TOTAL RHS per device (decimal counters: end - start) ──
                _rhs = {
                    'ME': round(max(_ec_safe_float(ev_end.get('me_hrs')) - _ec_safe_float(ev_start.get('me_hrs')), 0), 2),
                    'DG1': round(max(_ec_safe_float(ev_end.get('dg1_hrs')) - _ec_safe_float(ev_start.get('dg1_hrs')), 0), 2),
                    'DG2': round(max(_ec_safe_float(ev_end.get('dg2_hrs')) - _ec_safe_float(ev_start.get('dg2_hrs')), 0), 2),
                    'DG3': round(max(_ec_safe_float(ev_end.get('dg3_hrs')) - _ec_safe_float(ev_start.get('dg3_hrs')), 0), 2),
                    'BLR': round(max(_ec_safe_float(ev_end.get('boiler_hrs')) - _ec_safe_float(ev_start.get('boiler_hrs')), 0), 2),
                }
                _rhs['DGs'] = round(_rhs['DG1'] + _rhs['DG2'] + _rhs['DG3'], 2)

                # ── FUEL CONSUMPTION (ROB diff + bunkering in range) ──
                _hfo_start = _ec_safe_float(ev_start.get('hfo_rob'))
                _hfo_end = _ec_safe_float(ev_end.get('hfo_rob'))
                _do_start = _ec_safe_float(ev_start.get('do_rob'))
                _do_end = _ec_safe_float(ev_end.get('do_rob'))
                _hfo_bnkr = sum(_ec_safe_float(r.get('hfo_bnkr')) for _, r in range_df.iterrows())
                _do_bnkr = sum(_ec_safe_float(r.get('do_bnkr')) for _, r in range_df.iterrows())
                _hfo_cons = round(_hfo_start - _hfo_end + _hfo_bnkr, 2)
                _do_cons = round(_do_start - _do_end + _do_bnkr, 2)

                # Per-device fuel split for display (ME / DG1-3 / BLR)
                _fuel_df = range_df.iloc[1:].copy() if len(range_df) > 1 else range_df.iloc[0:0].copy()
                _me_hfo_raw = sum(_ec_safe_float(r.get('me_hfo_acc_cons')) for _, r in _fuel_df.iterrows())
                _me_do_raw = sum(_ec_safe_float(r.get('me_do_acc_cons')) for _, r in _fuel_df.iterrows())
                _dg_hfo_raw_total = sum(_ec_safe_float(r.get('dg_hfo_acc_cons')) for _, r in _fuel_df.iterrows())
                _dg_do_raw_total = sum(_ec_safe_float(r.get('dg_do_acc_cons')) for _, r in _fuel_df.iterrows())
                _blr_hfo_raw = sum(_ec_safe_float(r.get('blr_hfo_acc_cons')) for _, r in _fuel_df.iterrows())
                _blr_do_raw = sum(_ec_safe_float(r.get('blr_do_acc_cons')) for _, r in _fuel_df.iterrows())

                _dg_rhs_total = _rhs['DG1'] + _rhs['DG2'] + _rhs['DG3']
                if _dg_rhs_total > 0:
                    _dg1_hfo_raw = _dg_hfo_raw_total * _rhs['DG1'] / _dg_rhs_total
                    _dg2_hfo_raw = _dg_hfo_raw_total * _rhs['DG2'] / _dg_rhs_total
                    _dg3_hfo_raw = _dg_hfo_raw_total * _rhs['DG3'] / _dg_rhs_total
                    _dg1_do_raw = _dg_do_raw_total * _rhs['DG1'] / _dg_rhs_total
                    _dg2_do_raw = _dg_do_raw_total * _rhs['DG2'] / _dg_rhs_total
                    _dg3_do_raw = _dg_do_raw_total * _rhs['DG3'] / _dg_rhs_total
                else:
                    _dg1_hfo_raw = _dg2_hfo_raw = _dg3_hfo_raw = 0.0
                    _dg1_do_raw = _dg2_do_raw = _dg3_do_raw = 0.0

                _hfo_raw_total = _me_hfo_raw + _dg1_hfo_raw + _dg2_hfo_raw + _dg3_hfo_raw + _blr_hfo_raw
                _do_raw_total = _me_do_raw + _dg1_do_raw + _dg2_do_raw + _dg3_do_raw + _blr_do_raw

                if _hfo_raw_total > 0 and _hfo_cons > 0:
                    _hfo_scale = _hfo_cons / _hfo_raw_total
                    _me_hfo = round(_me_hfo_raw * _hfo_scale, 2)
                    _dg1_hfo = round(_dg1_hfo_raw * _hfo_scale, 2)
                    _dg2_hfo = round(_dg2_hfo_raw * _hfo_scale, 2)
                    _dg3_hfo = round(_dg3_hfo_raw * _hfo_scale, 2)
                    _blr_hfo = round(_blr_hfo_raw * _hfo_scale, 2)
                elif _hfo_cons > 0:
                    _sum_rhs_all = _rhs['ME'] + _rhs['DG1'] + _rhs['DG2'] + _rhs['DG3'] + _rhs['BLR']
                    if _sum_rhs_all > 0:
                        _me_hfo = round(_hfo_cons * _rhs['ME'] / _sum_rhs_all, 2)
                        _dg1_hfo = round(_hfo_cons * _rhs['DG1'] / _sum_rhs_all, 2)
                        _dg2_hfo = round(_hfo_cons * _rhs['DG2'] / _sum_rhs_all, 2)
                        _dg3_hfo = round(_hfo_cons * _rhs['DG3'] / _sum_rhs_all, 2)
                        _blr_hfo = round(_hfo_cons * _rhs['BLR'] / _sum_rhs_all, 2)
                    else:
                        _me_hfo = _dg1_hfo = _dg2_hfo = _dg3_hfo = _blr_hfo = 0.0
                else:
                    _me_hfo = _dg1_hfo = _dg2_hfo = _dg3_hfo = _blr_hfo = 0.0

                if _do_raw_total > 0 and _do_cons > 0:
                    _do_scale = _do_cons / _do_raw_total
                    _me_do = round(_me_do_raw * _do_scale, 2)
                    _dg1_do = round(_dg1_do_raw * _do_scale, 2)
                    _dg2_do = round(_dg2_do_raw * _do_scale, 2)
                    _dg3_do = round(_dg3_do_raw * _do_scale, 2)
                    _blr_do = round(_blr_do_raw * _do_scale, 2)
                elif _do_cons > 0:
                    # Fallback: distribute DO only to DGs (primary DO consumers),
                    # proportional to DG running hours — ME does not consume DO
                    _dg_rhs_for_do = _rhs['DG1'] + _rhs['DG2'] + _rhs['DG3']
                    if _dg_rhs_for_do > 0:
                        _me_do = 0.0
                        _blr_do = 0.0
                        _dg1_do = round(_do_cons * _rhs['DG1'] / _dg_rhs_for_do, 2)
                        _dg2_do = round(_do_cons * _rhs['DG2'] / _dg_rhs_for_do, 2)
                        _dg3_do = round(_do_cons * _rhs['DG3'] / _dg_rhs_for_do, 2)
                    else:
                        _me_do = _dg1_do = _dg2_do = _dg3_do = _blr_do = 0.0
                else:
                    _me_do = _dg1_do = _dg2_do = _dg3_do = _blr_do = 0.0

                _dg_hfo_disp = round(_dg1_hfo + _dg2_hfo + _dg3_hfo, 2)
                _dg_do_disp = round(_dg1_do + _dg2_do + _dg3_do, 2)

                # ── OIL CONSUMPTION (ROB diff + bunkering) ──
                _oil = {}
                for okey, rob_k, bnkr_k in [
                    ('me_sys', 'me_sys_rob', 'me_sys_bnkr'),
                    ('me_cyl', 'me_cyl_rob', 'me_cyl_bnkr'),
                    ('dg_sys', 'dg_sys_rob', 'dg_sys_bnkr'),
                ]:
                    s = _ec_safe_float(ev_start.get(rob_k))
                    e = _ec_safe_float(ev_end.get(rob_k))
                    b = sum(_ec_safe_float(r.get(bnkr_k)) for _, r in range_df.iterrows())
                    _oil[okey] = round(s - e + b, 2)

                # ── OIL ROB (from end event) ──
                _oil_rob = {
                    'me_sys': _ec_safe_float(ev_end.get('me_sys_rob')),
                    'me_cyl': _ec_safe_float(ev_end.get('me_cyl_rob')),
                    'dg_sys': _ec_safe_float(ev_end.get('dg_sys_rob')),
                }

                _fuel_rob = {
                    'hfo': _hfo_end,
                    'do': _do_end,
                    'ttl': round(_hfo_end + _do_end, 2),
                }

                # ── SCRUBBER RATIO (average sox_co2 in range) ──
                _sox_vals = [_ec_safe_float(r.get('sox_co2')) for _, r in range_df.iterrows()]
                _sox_nonzero = [v for v in _sox_vals if v > 0]
                _avg_sox = round(sum(_sox_nonzero) / len(_sox_nonzero), 2) if _sox_nonzero else 0

                # ── DG MWh (difference between end and start) ──
                _dg_mwh = {}
                for dg, k in [('DG1', 'dg1_mwh'), ('DG2', 'dg2_mwh'), ('DG3', 'dg3_mwh')]:
                    _dg_mwh[dg] = round(_ec_safe_float(ev_end.get(k)) - _ec_safe_float(ev_start.get(k)), 2)

                # ── AVG PWR / AVG RPM / TTL PWR / TTL RPM (end - start) ──
                _ttl_pwr = round(max(_ec_safe_float(ev_end.get('me_pwrmtr')) - _ec_safe_float(ev_start.get('me_pwrmtr')), 0), 2)
                _ttl_rpm = round(max(_ec_safe_float(ev_end.get('me_rev_c')) - _ec_safe_float(ev_start.get('me_rev_c')), 0), 2)
                _me_rhs_dec = _rhs['ME']
                _avg_pwr = round(_ttl_pwr / _me_rhs_dec, 2) if _me_rhs_dec > 0 else 0.0
                _avg_rpm = round(_ttl_rpm / (_me_rhs_dec * 60.0), 2) if _me_rhs_dec > 0 else 0.0

                # ── SCRUBBER OL / CL tracking ──
                def _ec_scrubber_tracking(sid, eid, range_df):
                    """Calculate time in Open Loop and Closed Loop."""
                    conn = None
                    try:
                        conn = get_connection()
                        prior_df = pd.read_sql_query(
                            "SELECT id, place, date, time FROM events WHERE id < ? ORDER BY id DESC",
                            conn, params=(sid,))
                    except Exception:
                        prior_df = pd.DataFrame()
                    finally:
                        if conn:
                            conn.close()
                    # Find last OL-CL or CL-OL before start
                    initial_mode = 'OL'  # default assume open loop
                    for _, pr in prior_df.iterrows():
                        p = str(pr.get('place', '')).upper()
                        if 'OL' in p and 'CL' in p:
                            # Determine direction: OL→CL means now in CL; CL→OL means now in OL
                            ol_pos = p.find('OL')
                            cl_pos = p.find('CL')
                            if ol_pos < cl_pos:
                                initial_mode = 'CL'  # OL→CL = scrubber switched to closed
                            else:
                                initial_mode = 'OL'  # CL→OL = scrubber switched to open
                            break

                    # Walk through range events and track mode switches using
                    # actual datetime intervals between consecutive events.
                    current_mode = initial_mode
                    ol_min = 0
                    cl_min = 0
                    _rows = [r for _, r in range_df.iterrows()]
                    for i, r in enumerate(_rows[:-1]):
                        _dt_cur = _ec_parse_dt(r)
                        _dt_nxt = _ec_parse_dt(_rows[i + 1])
                        if _dt_cur and _dt_nxt:
                            dur = max(0, int((_dt_nxt - _dt_cur).total_seconds() / 60))
                        else:
                            dur = _ec_hhmm_to_min(r.get('st_time'))
                        # This event's duration was spent in the CURRENT mode
                        if current_mode == 'OL':
                            ol_min += dur
                        else:
                            cl_min += dur
                        # Check if this event is a mode switch
                        p = str(r.get('place', '')).upper()
                        if 'OL' in p and 'CL' in p:
                            ol_pos = p.find('OL')
                            cl_pos = p.find('CL')
                            if ol_pos < cl_pos:
                                current_mode = 'CL'  # OL→CL
                            else:
                                current_mode = 'OL'  # CL→OL
                    return ol_min, cl_min

                _ol_min, _cl_min = _ec_scrubber_tracking(_ec_sid, _ec_eid, range_df)

                # ── Build HTML table (same style as Event Card Output) ──
                _ecv = _ec_fmt  # shortcut
                _ect_html = '''
                <style>
                .ect2 {width:100%;border-collapse:collapse;margin:0 0 2px 0;}
                .ect2 td {padding:2px 4px;font-size:12px;}
                .ect2 .sh {background:#2c3e50;color:#fff;font-weight:700;font-size:10px;text-align:center;padding:2px 6px;}
                .ect2 .sub {background:#ecf0f1;color:#2c3e50;font-weight:600;font-size:10px;text-align:center;}
                .ect2 .el {background:#f0f4f8;color:#2c3e50;font-weight:600;font-size:11px;text-align:right;white-space:nowrap;border:1px solid #dde;width:22%;}
                .ect2 .ev {background:#eaf2fb;color:#2c3e50;font-weight:600;font-size:12px;text-align:center;border:1px solid #b8d4f0;width:28%;}
                .ect2 .ttl {background:#d5e8d4;color:#2c3e50;font-weight:700;font-size:12px;text-align:center;border:1px solid #b8d4f0;}
                </style>
                '''

                # Section 1: TTL TIME + TOTAL RHS + FUEL CONSUMPTION
                _ect_html += f'''
                <table class="ect2">
                <tr><td class="sh" colspan="4">EVENT CALCULATOR  ID {_ec_sid} → {_ec_eid}</td></tr>
                <tr><td class="el">TTL TIME</td><td class="ttl" colspan="3">{round(_ttl_min/60, 2)} h</td></tr>
                <tr><td class="sh" colspan="2">TOTAL RHS</td><td class="sh" colspan="2">FUEL CONSUMPTION</td></tr>
                <tr><td class="sub">DEVICE</td><td class="sub">RHS</td><td class="sub ev-hfo">HFO</td><td class="sub ev-do">DO</td></tr>
                <tr><td class="el">M/E</td><td class="ev">{_ecv(_rhs["ME"])}</td>
                    <td class="ev ev-hfo">{_ecv(_me_hfo)}</td><td class="ev ev-do">{_ecv(_me_do)}</td></tr>
                <tr><td class="el">D/G#1</td><td class="ev">{_ecv(_rhs["DG1"])}</td><td class="ev ev-hfo">{_ecv(_dg1_hfo)}</td><td class="ev ev-do">{_ecv(_dg1_do)}</td></tr>
                <tr><td class="el">D/G#2</td><td class="ev">{_ecv(_rhs["DG2"])}</td><td class="ev ev-hfo">{_ecv(_dg2_hfo)}</td><td class="ev ev-do">{_ecv(_dg2_do)}</td></tr>
                <tr><td class="el">D/G#3</td><td class="ev">{_ecv(_rhs["DG3"])}</td><td class="ev ev-hfo">{_ecv(_dg3_hfo)}</td><td class="ev ev-do">{_ecv(_dg3_do)}</td></tr>
                <tr><td class="el">D/G's</td><td class="ev">{_ecv(_rhs["DGs"])}</td><td class="ev ev-hfo">{_ecv(_dg_hfo_disp)}</td><td class="ev ev-do">{_ecv(_dg_do_disp)}</td></tr>
                <tr><td class="el">BLR</td><td class="ev">{_ecv(_rhs["BLR"])}</td><td class="ev ev-hfo">{_ecv(_blr_hfo)}</td><td class="ev ev-do">{_ecv(_blr_do)}</td></tr>
                <tr><td class="el">ST_TIME</td><td class="ev">{_ttl_time_s}</td><td class="ev ev-hfo">{_ecv(_hfo_cons)}</td><td class="ev ev-do">{_ecv(_do_cons)}</td></tr>
                </table>
                '''

                # Section 2: FUEL ROB + OIL CONSUMPTION
                _ect_html += f'''
                <table class="ect2">
                <tr><td class="sh" colspan="2">FUEL ROB</td><td class="sh" colspan="2">OIL CONSUMPTION</td></tr>
                <tr><td class="el el-hfo">HFO</td><td class="ev ev-hfo">{_ecv(_fuel_rob["hfo"])}</td>
                    <td class="el el-oil">M/E SYS</td><td class="ev ev-oil">{_ecv(_oil["me_sys"])}</td></tr>
                <tr><td class="el el-do">DO</td><td class="ev ev-do">{_ecv(_fuel_rob["do"])}</td>
                    <td class="el el-oil">M/E CYL</td><td class="ev ev-oil">{_ecv(_oil["me_cyl"])}</td></tr>
                <tr><td class="el">TTL</td><td class="ev">{_ecv(_fuel_rob["ttl"])}</td>
                    <td class="el el-oil">D/G SYS</td><td class="ev ev-oil">{_ecv(_oil["dg_sys"])}</td></tr>
                </table>
                '''

                # Section 3: POWER PROD + OIL ROB
                _ect_html += f'''
                <table class="ect2">
                <tr><td class="sh" colspan="2">POWER PRODUCTION</td><td class="sh" colspan="2">OIL ROB</td></tr>
                <tr><td class="el">D/G#1</td><td class="ev">{_ecv(_dg_mwh["DG1"])}</td>
                    <td class="el el-oil">M/E SYS</td><td class="ev ev-oil">{_ecv(_oil_rob["me_sys"])}</td></tr>
                <tr><td class="el">D/G#2</td><td class="ev">{_ecv(_dg_mwh["DG2"])}</td>
                    <td class="el el-oil">M/E CYL</td><td class="ev ev-oil">{_ecv(_oil_rob["me_cyl"])}</td></tr>
                <tr><td class="el">D/G#3</td><td class="ev">{_ecv(_dg_mwh["DG3"])}</td>
                    <td class="el el-oil">D/G SYS</td><td class="ev ev-oil">{_ecv(_oil_rob["dg_sys"])}</td></tr>
                </table>
                '''

                # Section 4: M/E PARAMS
                _ect_html += f'''
                <table class="ect2">
                <tr><td class="sh" colspan="4">M/E PARAMETERS</td></tr>
                <tr><td class="el">AVG PWR</td><td class="ev">{_ecv(_avg_pwr)}</td>
                    <td class="el">TTL PWR</td><td class="ev">{_ecv(_ttl_pwr)}</td></tr>
                <tr><td class="el">AVG RPM</td><td class="ev">{_ecv(_avg_rpm)}</td>
                    <td class="el">TTL RPM</td><td class="ev">{_ecv(_ttl_rpm)}</td></tr>
                </table>
                '''

                # Section 5: SCRUBBER (moved to bottom)
                _ect_html += f'''
                <table class="ect2">
                <tr><td class="sh" colspan="4">SCRUBBER</td></tr>
                <tr><td class="el">RATIO</td><td class="ev">{_ecv(_avg_sox)}</td>
                    <td class="el">OPEN</td><td class="ev">{_ec_min_to_hhmm(_ol_min)}</td></tr>
                <tr><td class="el">CLOSE</td><td class="ev">{_ec_min_to_hhmm(_cl_min)}</td>
                    <td class="el">TOTAL</td><td class="ev">{_ec_min_to_hhmm(_ol_min + _cl_min)}</td></tr>
                </table>
                '''

                st.markdown(_ect_html, unsafe_allow_html=True)

                # Validation row
                _scrub_total = _ol_min + _cl_min
                if _scrub_total > 0 and abs(_scrub_total - _ttl_min) > 1:
                    st.toast(f"⚠ Scrubber OL+CL ({_ec_min_to_hhmm(_scrub_total)}) ≠ TTL TIME ({_ttl_time_s})", icon="⚠️")
            else:
                st.info("Invalid event IDs. Check start/end range.")
          else:
            if _ec_sid < 2:
                st.caption("Start ID must be ≥ 2 (ID 1 is seed)")
            elif _ec_eid < _ec_sid:
                st.caption("End ID must be ≥ Start ID")
        except Exception as _ec_err:
            st.caption(f"Calculator: refresh page if data missing")

    else:
        st.info("No events yet. Use INPUT CARD to add entries.")
        if st.button("\u2795 NEW ENTRY", type="secondary"):
            st.session_state.editing_id = None
            st.session_state.new_entry_mode = True
            st.rerun()
