import os
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def setup():
    root = Path(__file__).resolve().parent
    env_path = root / ".env"
    env_example = root / ".env.example"

    if not env_path.exists() and env_example.exists():
        print("'.env' файл олдсонгүй. '.env.example'-аас үүсгэж байна...")
        password = input("PostgreSQL суулгахдаа өгсөн 'postgres' хэрэглэгчийн нууц үгээ (password) оруулна уу: ").strip()
        
        example_content = env_example.read_text(encoding="utf-8")
        new_content = example_content.replace("CHANGE_ME", password)
        env_path.write_text(new_content, encoding="utf-8")
        print("'.env' файл амжилттай үүслээ.")

    load_dotenv(dotenv_path=env_path)
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Холболтын хаяг (DATABASE_URL) олдсонгүй.")
        return

    # postgres үндсэн систем рүү холбогдож fintrack бааз үүсгэх
    base_url = db_url.rsplit('/', 1)[0] + '/postgres'
    
    print("PostgreSQL серверт холбогдож байна...")
    try:
        engine = create_engine(base_url, isolation_level="AUTOCOMMIT")
        with engine.connect() as conn:
            res = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'fintrack'")).fetchone()
            if not res:
                conn.execute(text("CREATE DATABASE fintrack"))
                print("'fintrack' өгөгдлийн сан амжилттай үүслээ!")
            else:
                print("'fintrack' өгөгдлийн сан аль хэдийн үүссэн байна.")
    except Exception as e:
        print(f"Өгөгдлийн сан үүсгэхэд алдаа гарлаа: {e}")
        print("PostgreSQL сервер ажиллаж байгаа эсэх болон нууц үг зөв эсэхийг шалгана уу.")
        return

    # Хүснэгтүүдийг үүсгэх болон өгөгдөл seed хийх
    from core.db import init_db
    from core.seed import seed
    print("Өгөгдлийн сангийн хүснэгтүүдийг үүсгэж байна...")
    init_db()
    print("Үндсэн өгөгдөл (categories & rules)-г оруулж байна...")
    seed()
    print("\n БҮХ ЗҮЙЛ АМЖИЛТТАЙ БЭЛЭН БОЛЛОО!")
    print("Одоо терминал дээр доорх комантыг бичиж програмаа ажиллуулаарай:")
    print("streamlit run app.py")

if __name__ == "__main__":
    setup()
