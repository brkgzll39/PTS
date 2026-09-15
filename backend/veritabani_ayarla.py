"""Configure the PTS database URL for a SQL Server installation."""
import argparse
import getpass
import json
import os
from urllib.parse import quote_plus

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_YOLU = os.path.join(BACKEND_DIR, "database_config.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="PTS SQL Server bağlantısını ayarla")
    parser.add_argument("--sunucu", required=True, help="SQL Server adresi, örn. localhost\\SQLEXPRESS")
    parser.add_argument("--veritabani", default="PTS", help="Veritabanı adı")
    parser.add_argument("--kullanici", required=True, help="SQL kullanıcı adı")
    args = parser.parse_args()
    parola = getpass.getpass("SQL parolası: ")
    connection_string = ";".join([
        "DRIVER={ODBC Driver 18 for SQL Server}",
        f"SERVER={args.sunucu}",
        f"DATABASE={args.veritabani}",
        f"UID={args.kullanici}",
        f"PWD={parola}",
        "Encrypt=no",
        "TrustServerCertificate=yes",
    ])
    url = f"mssql+pyodbc:///?odbc_connect={quote_plus(connection_string)}"
    with open(CONFIG_YOLU, "w", encoding="utf-8") as dosya:
        json.dump({"database_url": url}, dosya, indent=2)
    print(f"SQL Server bağlantısı kaydedildi: {args.sunucu}/{args.veritabani}")


if __name__ == "__main__":
    main()
