try:
    import psycopg2
    _PSYCOPG2_AVAILABLE = True
except ImportError:
    _PSYCOPG2_AVAILABLE = False

import _helpers.config as _cfg

_DB_QUERY_LIMIT = 5  # max rows fetched per table in diagnostic queries


def _query_subscription_from_db(token: str) -> list[dict]:
    """Query DB for subscription data by recurrent_token UUID.

    Lookup chain:
      support.recurrent_token (token → tran_id)
      → secure.recurrents (subscription record: status, period, validity)
    """
    if not _PSYCOPG2_AVAILABLE or not _cfg.DB_HOST or not token:
        return []
    results = []
    try:
        sp = psycopg2.connect(host=_cfg.DB_HOST, port=_cfg.DB_PORT, dbname="support", user=_cfg.DB_USER, password=_cfg.DB_PASSWORD)
        sc = psycopg2.connect(host=_cfg.DB_HOST, port=_cfg.DB_PORT, dbname="secure",  user=_cfg.DB_USER, password=_cfg.DB_PASSWORD)
        sp_cur = sp.cursor()
        sc_cur = sc.cursor()

        tran_id = None
        try:
            sp_cur.execute("SELECT id, tran_id, token FROM public.recurrent_token WHERE token = %s LIMIT 1", (token,))
            rows = sp_cur.fetchall()
            if rows:
                cols = [d[0] for d in sp_cur.description]
                results.append({"db": "support", "table": "recurrent_token", "columns": cols, "rows": rows})
                tran_id = rows[0][1]
        except Exception:
            sp.rollback()

        if tran_id:
            try:
                sc_cur.execute(f"SELECT * FROM public.recurrents WHERE transaction_id = %s LIMIT {_DB_QUERY_LIMIT}", (tran_id,))
                rows = sc_cur.fetchall()
                if rows:
                    cols = [d[0] for d in sc_cur.description]
                    results.append({"db": "secure", "table": "recurrents", "columns": cols, "rows": rows})
            except Exception:
                sc.rollback()

        sp.close()
        sc.close()
    except Exception:
        pass
    return results


def _query_paylink_from_db(link_id: str) -> list[dict]:
    """Query support DB for payment link data. Returns list of {db, table, columns, rows}."""
    if not _PSYCOPG2_AVAILABLE or not _cfg.DB_HOST or not link_id:
        return []
    results = []
    try:
        conn = psycopg2.connect(
            host=_cfg.DB_HOST, port=_cfg.DB_PORT, dbname="support",
            user=_cfg.DB_USER, password=_cfg.DB_PASSWORD,
        )
        for table, col in [("webpayv3", "id")]:
            try:
                cur = conn.cursor()
                cur.execute(
                    f"SELECT * FROM public.{table} WHERE {col} = %s LIMIT 1",
                    (link_id,),
                )
                rows = cur.fetchall()
                if rows:
                    cols = [d[0] for d in cur.description]
                    results.append({"db": "support", "table": table, "columns": cols, "rows": rows})
                cur.close()
            except Exception:
                conn.rollback()
        conn.close()
    except Exception:
        pass
    return results


def _query_transaction_from_db(tr_id: int) -> list[dict]:
    """Query both DBs for transaction data. Returns list of {db, table, columns, rows}."""
    if not _PSYCOPG2_AVAILABLE or not _cfg.DB_HOST:
        return []
    results = []
    try:
        sc = psycopg2.connect(host=_cfg.DB_HOST, port=_cfg.DB_PORT, dbname="secure", user=_cfg.DB_USER, password=_cfg.DB_PASSWORD)
        sp = psycopg2.connect(host=_cfg.DB_HOST, port=_cfg.DB_PORT, dbname="support", user=_cfg.DB_USER, password=_cfg.DB_PASSWORD)
        sc_cur = sc.cursor()
        sp_cur = sp.cursor()

        card_id = None

        queries = [
            (sc_cur, "secure",  "transactions",            "id",             tr_id),
            (sc_cur, "secure",  "transactions_history",    "trans_id",       tr_id),
            (sp_cur, "support", "bapi_tr_fields",          "tr_id",          tr_id),
            (sp_cur, "support", "limits_transaction_info", "tran_id",        tr_id),
            (sp_cur, "support", "receipt",                 "tran_id",        tr_id),
            (sp_cur, "support", "meta_transaction",        "transaction_id", tr_id),
            (sp_cur, "support", "af_data",                 "tr_id",          tr_id),
            (sp_cur, "support", "ui_interactions",         "transaction_id", tr_id),
        ]

        for cur, db, table, col, val in queries:
            try:
                cur.execute(f'SELECT * FROM public."{table}" WHERE "{col}" = %s LIMIT {_DB_QUERY_LIMIT}', (val,))
                rows = cur.fetchall()
                if rows:
                    cols = [d[0] for d in cur.description]
                    results.append({"db": db, "table": table, "columns": cols, "rows": rows})
                    if table == "transactions":
                        idx = cols.index("card_id") if "card_id" in cols else -1
                        if idx >= 0:
                            card_id = rows[0][idx]
            except Exception:
                pass

        if card_id:
            try:
                sc_cur.execute(
                    "SELECT id, key_id, cardholder, expiration_date FROM public.card_storage WHERE id = %s",
                    (str(card_id),)
                )
                rows = sc_cur.fetchall()
                if rows:
                    cols = [d[0] for d in sc_cur.description]
                    results.append({"db": "secure", "table": "card_storage", "columns": cols, "rows": rows})
            except Exception:
                pass

        sc.close()
        sp.close()
    except Exception:
        pass
    return results
