import numpy as np
import os
import json
import pandas as pd

from datetime import datetime, timezone
from pathlib import Path

import logging
logger = logging.getLogger(__name__)
import re

from urllib.parse import urlparse

from flask import (
    Flask,
    jsonify,
    request,
    render_template,
    redirect,
    url_for,
    send_file,
)
from io import BytesIO
from werkzeug.utils import secure_filename

from web.auth.routes import auth
from web.auth.database import (
    current_user_id,
    get_connection,
    init_database,
)

from scraper.scraper import scrape_products
from scraper.fetcher import (
    analysis_deadline,
)

from analysis.price_analysis import (
    clean_product_data,
    calculate_price_statistics,
    get_product_insights,
)


def load_local_environment():
    """
    Load simple KEY=VALUE settings from the project .env
    without overriding process environment.
    """

    env_path = Path(__file__).resolve().parent.parent / ".env"

    if not env_path.is_file():
        return

    try:
        lines = env_path.read_text(
            encoding="utf-8"
        ).splitlines()

    except OSError:
        logging.getLogger(__name__).warning(
            "Local .env could not be read; using process environment only"
        )
        return

    for line in lines:

        line = line.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[7:].lstrip()

        key, separator, value = line.partition("=")

        key = key.strip()
        value = value.strip()

        if (
            not separator
            or not re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*",
                key
            )
        ):
            continue

        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in "\"'"
        ):
            value = value[1:-1]

        os.environ.setdefault(key, value)


load_local_environment()


app = Flask(__name__)


configured_secret = os.environ.get(
    "PRICE_ANALYZER_SECRET_KEY"
)


if (
    os.environ.get("FLASK_ENV") == "production"
    and (
        not configured_secret
        or configured_secret.startswith("replace-with-")
    )
):
    raise RuntimeError(
        "Set a private PRICE_ANALYZER_SECRET_KEY "
        "before running PriceLens in production."
    )


app.config.update(
    SECRET_KEY=(
        configured_secret
        or "local-development-key-change-before-deployment"
    ),

    SESSION_COOKIE_HTTPONLY=True,

    SESSION_COOKIE_SAMESITE="Lax",

    SESSION_COOKIE_SECURE=(
        os.environ.get("FLASK_ENV") == "production"
    ),

    MAX_CONTENT_LENGTH=6 * 1024 * 1024,
)


app.register_blueprint(auth)

init_database()


# =========================================================
# AUTHENTICATED PAGE HELPER
# =========================================================

def authenticated_page(template):

    if not current_user_id():
        return redirect(url_for("login_page"))

    return render_template(template)


# =========================================================
# DATA CONVERSION HELPER
# =========================================================

def convert_to_python(value):
    """
    Convert NumPy/Pandas/SQLite values into standard Python values
    that Flask can serialize as JSON.
    """

    # SQLite can contain NumPy numeric values as raw bytes.
    # A float64 is stored as 8 bytes.
    if isinstance(value, bytes):
        if len(value) == 8:
            try:
                return float(
                    np.frombuffer(
                        value,
                        dtype=np.float64
                    )[0]
                )
            except (TypeError, ValueError):
                pass

        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.bool_):
        return bool(value)

    if isinstance(value, np.floating):
        return float(value)

    if isinstance(value, np.ndarray):
        return value.tolist()

    if isinstance(value, dict):
        return {
            key: convert_to_python(val)
            for key, val in value.items()
        }

    if isinstance(value, list):
        return [
            convert_to_python(item)
            for item in value
        ]

    # Convert NaN/NaT values into JSON null.
    try:
        if np.isnan(value):
            return None
    except (TypeError, ValueError):
        pass

    return value

# =========================================================
# PUBLIC PAGES
# =========================================================

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/signup")
def signup_page():
    return render_template("signup.html")


@app.route("/forgot-password")
def forgot_password_page():
    return render_template("forgot_password.html")


# =========================================================
# AUTHENTICATED MAIN PAGES
# =========================================================

@app.route("/dashboard")
def dashboard_page():
    return authenticated_page("dashboard.html")


@app.route("/import")
def import_page():
    return authenticated_page("import.html")


@app.route("/profile")
def profile_page():
    return authenticated_page("profile.html")


@app.route("/history")
def history_page():
    return authenticated_page("history.html")


@app.route("/analysis/<int:analysis_id>/price-comparison")
def analysis_price_page(analysis_id):
    return authenticated_page("analysis_price.html")


@app.route("/analysis/<int:analysis_id>/price-distribution")
def analysis_distribution_page(analysis_id):
    return authenticated_page("analysis_distribution.html")


@app.route("/analysis/<int:analysis_id>/price-rating")
def analysis_rating_page(analysis_id):
    return authenticated_page("analysis_rating.html")


@app.route("/analysis/<int:analysis_id>/price-statistics")
def analysis_statistics_page(analysis_id):
    return authenticated_page("analysis_statistics.html")


@app.route("/analysis/<int:analysis_id>/products")
def analysis_products_page(analysis_id):
    return authenticated_page("analysis_products.html")


# =========================================================
# HEALTH API
# =========================================================

@app.route("/api/health", methods=["GET"])
def health():

    return jsonify({
        "status": "ok",
        "message": "Product Price Analysis API is running"
    })


# =========================================================
# ANALYSIS API
# =========================================================

@app.route("/api/analyze", methods=["POST"])
def analyze():

    # -----------------------------
    # Check authentication
    # -----------------------------

    user_id = current_user_id()

    if not user_id:

        return jsonify({
            "error": "Authentication required."
        }), 401


    # -----------------------------
    # Read request data
    # -----------------------------

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "error": "A JSON object is required."
        }), 400


    url = data.get("url", "")

    if not isinstance(url, str):
        return jsonify({
            "error": "Website URL must be text."
        }), 400


    url = url.strip()

    pages = data.get("pages", 1)


    if (
        isinstance(pages, bool)
        or (
            isinstance(pages, float)
            and not pages.is_integer()
        )
    ):
        return jsonify({
            "error": "Pages must be a whole number."
        }), 400


    if not url:

        return jsonify({
            "error": "Website URL is required."
        }), 400


    try:

        pages = int(pages)

    except (TypeError, ValueError):

        return jsonify({
            "error": "Pages must be an integer."
        }), 400


    if pages < 1 or pages > 20:

        return jsonify({
            "error": "Pages must be between 1 and 20."
        }), 400


    # -----------------------------
    # Scraping + cleaning
    # -----------------------------

    try:

        with analysis_deadline(90):

            products = scrape_products(
                url,
                pages=pages
            )


        if not products:

            return jsonify({
                "error": (
                    "The page was accessible, but no "
                    "product information could be identified."
                ),
                "status": "FAILED",
            }), 404


        pages_scraped = getattr(products, "pages_scraped", pages)
        pages_requested = getattr(products, "pages_requested", pages)
        page_product_counts = getattr(products, "page_product_counts", [])
        df, cleaning_report = clean_product_data(products, return_report=True)

        logger.debug("[API DEBUG] Scraped products:", len(products))
        logger.debug("[API DEBUG] Cleaned products:", len(df))


        if df.empty:

            return jsonify({
                "error": (
                    "Product information was found, "
                    "but no valid prices remained after cleaning."
                ),
                "status": "PARTIAL",
            }), 422


        # -----------------------------
        # Analysis
        # -----------------------------

        currencies = sorted({
            str(value).strip()
            for value in df["currency"].dropna()
            if str(value).strip()
        })


        mixed_currencies = (
            len(currencies) > 1
            or (
                bool(currencies)
                and df["currency"].isna().any()
            )
        )


        statistics = (
            calculate_price_statistics(df)
            if not mixed_currencies
            else {
                "minimum_price": None,
                "maximum_price": None,
                "average_price": None,
                "median_price": None,
                "price_difference": None,
            }
        )


        insights = (
            get_product_insights(df)
            if not mixed_currencies
            else {
                "highest_rated_product": None,
                "lowest_priced_product": None,
                "most_expensive_product": None,
            }
        )


        # -----------------------------
        # Convert product data
        # -----------------------------

        products_data = df.to_dict(
            orient="records"
        )

        logger.debug("[API DEBUG] Response products:", len(products_data))


        source_name = next(
            (
                str(item.get("website_name")).strip()
                for item in products_data
                if item.get("website_name")
            ),
            (
                urlparse(url)
                .hostname
                or "Unknown source"
            ).removeprefix("www."),
        )


        products_json = json.dumps(
            convert_to_python(products_data),
            allow_nan=False
        )


        result_status = (
            "PARTIAL"
            if len(df) < len(products) or pages_scraped < pages_requested
            else "SUCCESS"
        )


        # -----------------------------
        # Save analysis history
        # -----------------------------

        connection = get_connection()

        try:

            connection.execute(
                """
                INSERT INTO analysis_history (
                    user_id,
                    source_url,
                    pages_scraped,
                    products_found,
                    minimum_price,
                    maximum_price,
                    average_price,
                    median_price,
                    currency,
                    source_name,
                    products_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    url,
                    pages_scraped,
                    len(df),
                    statistics["minimum_price"],
                    statistics["maximum_price"],
                    statistics["average_price"],
                    statistics["median_price"],
                    currencies[0]
                    if len(currencies) == 1
                    else None,
                    source_name,
                    products_json,
                )
            )


            analysis_id = connection.execute(
                "SELECT last_insert_rowid()"
            ).fetchone()[0]


            connection.commit()


        finally:

            connection.close()


        # -----------------------------
        # Return results
        # -----------------------------

        return jsonify(
            convert_to_python({

                "success": True,

                "products": products_data,

                "statistics": statistics,

                "insights": insights,

                "currency": (
                    currencies[0]
                    if len(currencies) == 1
                    else None
                ),

                "currencies": currencies,

                "currency_warning": mixed_currencies,

                "status": result_status,

                "pages_scraped": pages_scraped,

                "pages_requested": pages_requested,

                "page_product_counts": page_product_counts,

                "cleaning_report": cleaning_report,

                "source_name": source_name,

                "source_url": url,

                "analysis_id": analysis_id,

                "analyzed_at": (
                    datetime.now(timezone.utc)
                    .isoformat()
                ),
            })
        )


    except ValueError as error:

        return jsonify({
            "error": str(error)
        }), 400


    except RuntimeError as error:

        message = str(error)

        lowered = message.lower()

        restricted = any(
            term in lowered
            for term in (
                "robots.txt",
                "disallowed",
                "access challenge",
                "denied or rate-limited",
                "captcha",
            )
        )


        if restricted:

            return jsonify({
                "error": (
                    "This website restricts automated access. "
                    "It may require JavaScript, login, CAPTCHA, "
                    "or block scrapers."
                ),
                "detail": message,
                "status": "RESTRICTED",
            }), 403


        return jsonify({
            "error": message,
            "status": "FAILED",
        }), 502


    except Exception:

        app.logger.exception(
            "Unexpected error while analyzing a product page"
        )

        return jsonify({
            "error": "The analysis could not be completed."
        }), 500



@app.route("/api/import", methods=["POST"])
def import_products():
    """Import CSV or Excel product rows through the existing cleaning/analysis pipeline."""
    user_id = current_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required."}), 401

    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"error": "Choose a CSV or Excel file."}), 400

    filename = secure_filename(upload.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".xlsx"}:
        return jsonify({"error": "Only .csv and .xlsx files are supported."}), 400

    payload = upload.stream.read(5 * 1024 * 1024 + 1)
    if len(payload) > 5 * 1024 * 1024:
        return jsonify({"error": "Files must be 5 MB or smaller."}), 413

    try:
        frame = (pd.read_csv(BytesIO(payload), encoding="utf-8-sig")
                 if suffix == ".csv"
                 else pd.read_excel(BytesIO(payload), engine="openpyxl"))
    except Exception:
        return jsonify({"error": "The file could not be read. Check that it is a valid CSV or .xlsx workbook."}), 400

    if frame.empty:
        return jsonify({"error": "The file contains no product rows."}), 400
    if len(frame) > 10000:
        return jsonify({"error": "Files may contain at most 10,000 product rows."}), 400

    products = frame.where(pd.notna(frame), None).to_dict(orient="records")
    cleaned, cleaning_report = clean_product_data(products, return_report=True)
    if cleaned.empty:
        return jsonify({"error": "No rows with valid product prices remained after cleaning."}), 422

    currencies = sorted({str(value).strip() for value in cleaned["currency"].dropna() if str(value).strip()})
    mixed = len(currencies) > 1 or (bool(currencies) and cleaned["currency"].isna().any())
    statistics = calculate_price_statistics(cleaned) if not mixed else {
        "minimum_price": None, "maximum_price": None, "average_price": None,
        "median_price": None, "price_difference": None,
    }
    insights = get_product_insights(cleaned) if not mixed else {
        "highest_rated_product": None, "lowest_priced_product": None,
        "most_expensive_product": None,
    }
    records = cleaned.to_dict(orient="records")
    products_json = json.dumps(convert_to_python(records), allow_nan=False)
    source_name = f"Imported file: {filename}"
    source_url = f"Imported file: {filename}"
    connection = get_connection()
    try:
        connection.execute("""
            INSERT INTO analysis_history (
                user_id, source_url, pages_scraped, products_found, minimum_price,
                maximum_price, average_price, median_price, currency, source_name, products_json
            ) VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, source_url, len(cleaned), statistics["minimum_price"],
              statistics["maximum_price"], statistics["average_price"],
              statistics["median_price"], currencies[0] if len(currencies) == 1 else None,
              source_name, products_json))
        analysis_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.commit()
    finally:
        connection.close()

    return jsonify(convert_to_python({
        "success": True, "products": records, "statistics": statistics,
        "insights": insights, "currency": currencies[0] if len(currencies) == 1 else None,
        "currencies": currencies, "currency_warning": mixed,
        "status": "SUCCESS", "source_name": source_name, "source_url": source_url,
        "analysis_id": analysis_id, "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "cleaning_report": cleaning_report,
    }))


@app.route("/api/history/<int:analysis_id>/export/<file_format>", methods=["GET"])
def export_history(analysis_id, file_format):
    """Download one of the signed-in user's saved analyses as CSV or Excel."""
    user_id = current_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required."}), 401
    if file_format not in {"csv", "xlsx"}:
        return jsonify({"error": "Choose csv or xlsx format."}), 400

    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT products_json FROM analysis_history WHERE id = ? AND user_id = ?",
            (analysis_id, user_id),
        ).fetchone()
    finally:
        connection.close()
    if not row:
        return jsonify({"error": "Analysis was not found."}), 404

    frame = pd.DataFrame(json.loads(row["products_json"] or "[]"))
    # Prevent untrusted scraped/imported text from becoming spreadsheet formulas.
    for column in frame.select_dtypes(include=["object", "string"]).columns:
        frame[column] = frame[column].map(
            lambda value: "'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value
        )
    output = BytesIO()
    if file_format == "csv":
        frame.to_csv(output, index=False, encoding="utf-8-sig")
        mimetype, extension = "text/csv; charset=utf-8", "csv"
    else:
        frame.to_excel(output, index=False, engine="openpyxl")
        mimetype, extension = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
    output.seek(0)
    return send_file(output, mimetype=mimetype, as_attachment=True,
                     download_name=f"pricelens-analysis-{analysis_id}.{extension}")

# =========================================================
# HISTORY LIST API
# =========================================================

@app.route("/api/history", methods=["GET"])
def history():

    user_id = current_user_id()

    if not user_id:

        return jsonify({
            "error": "Authentication required."
        }), 401


    connection = get_connection()

    try:

        rows = connection.execute(
            """
            SELECT
                id,
                source_url,
                pages_scraped,
                products_found,
                minimum_price,
                maximum_price,
                average_price,
                median_price,
                currency,
                source_name,
                analyzed_at
            FROM analysis_history
            WHERE user_id = ?
            ORDER BY analyzed_at DESC
            """,
            (user_id,)
        ).fetchall()


        return jsonify(
            convert_to_python({
                "success": True,
                "history": [
                    dict(row)
                    for row in rows
                ]
            })
        )


    finally:

        connection.close()


# =========================================================
# 404
# =========================================================

@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404


# =========================================================
# HISTORY DETAIL API
# =========================================================

@app.route(
    "/api/history/<int:analysis_id>",
    methods=["GET"]
)
def history_detail(analysis_id):

    user_id = current_user_id()

    if not user_id:

        return jsonify({
            "error": "Authentication required."
        }), 401


    connection = get_connection()

    try:

        row = connection.execute(
            """
            SELECT
                id,
                source_url,
                source_name,
                pages_scraped,
                products_found,
                currency,
                analyzed_at,
                products_json
            FROM analysis_history
            WHERE id = ?
              AND user_id = ?
            """,
            (
                analysis_id,
                user_id
            ),
        ).fetchone()


        if not row:

            return jsonify({
                "error": "Analysis was not found."
            }), 404


        result = dict(row)


        result["products"] = json.loads(
            result.pop("products_json") or "[]"
        )


        prices = [
            item["price"]
            for item in result["products"]
            if item.get("price") is not None
        ]


        currencies = sorted({
            str(item.get("currency")).strip()
            for item in result["products"]
            if item.get("currency")
        })


        currency_warning = (
            len(currencies) > 1
            or (
                bool(currencies)
                and any(
                    not item.get("currency")
                    for item in result["products"]
                )
            )
        )


        statistics = (
            calculate_price_statistics(
                pd.DataFrame(result["products"])
            )
            if prices and not currency_warning
            else {
                "minimum_price": None,
                "maximum_price": None,
                "average_price": None,
                "median_price": None,
                "price_difference": None,
            }
        )


        products_df = pd.DataFrame(
            result["products"]
        )


        insights = (
            get_product_insights(products_df)
            if prices and not currency_warning
            else {
                "highest_rated_product": None,
                "lowest_priced_product": None,
                "most_expensive_product": None,
            }
        )


        return jsonify(
            convert_to_python({

                "success": True,

                "products": result["products"],

                "statistics": statistics,

                "insights": insights,

                "currency": result["currency"],

                "currencies": currencies,

                "currency_warning": currency_warning,

                "source_name": result["source_name"],

                "source_url": result["source_url"],

                "analysis_id": result["id"],

                "analyzed_at": result["analyzed_at"],

                "status": "SUCCESS",

            })
        )


    finally:

        connection.close()


# =========================================================
# RUN SERVER
# =========================================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
