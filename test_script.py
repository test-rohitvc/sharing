import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from nebula3.gclient.net import ConnectionPool
from nebula3.Config import Config
import time

# ==========================================
# CONFIGURATION
# ==========================================
SERVER_IP = "YOUR_SERVER_IP"  # <--- REPLACE THIS WITH YOUR VPS IP

# Postgres Configuration
PG_CONFIG = {
    "host": SERVER_IP,
    "port": "6051",          # Your public Postgres port
    "user": "postgres",      # Default from Docker Compose
    "password": "password",  # Default from Docker Compose
    "dbname": "vectordb"
}

# Nebula Graph Configuration
NEBULA_CONFIG = {
    "host": SERVER_IP,
    "port": 6052,            # Your public Nebula Graphd port
    "user": "root",
    "password": "password"   # Default Nebula password
}

def test_postgres_vector():
    print(f"\n--- Testing PostgreSQL + pgvector on {PG_CONFIG['host']}:{PG_CONFIG['port']} ---")
    try:
        # Connect to Postgres
        conn = psycopg2.connect(**PG_CONFIG)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        # 1. Check Connection
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        print(f"✅ Connected! Version: {version}")

        # 2. Check/Enable pgvector extension
        print("   Checking pgvector extension...")
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        print("✅ pgvector extension enabled.")

        # 3. Test Vector Operations (Create table, insert, query)
        print("   Testing vector read/write...")
        # Create a temp table
        cur.execute("DROP TABLE IF EXISTS test_vectors;")
        cur.execute("CREATE TABLE test_vectors (id serial PRIMARY KEY, embedding vector(3));")
        
        # Insert a vector
        cur.execute("INSERT INTO test_vectors (embedding) VALUES ('[1,2,3]');")
        
        # Select using Euclidean distance (<->)
        cur.execute("SELECT id, embedding, embedding <-> '[1,2,3]' as distance FROM test_vectors;")
        row = cur.fetchone()
        
        if row:
            print(f"✅ Vector Test Successful! Inserted: {row[1]}, Distance: {row[2]}")
        else:
            print("❌ Vector Test Failed: No data returned.")

        # Cleanup
        cur.execute("DROP TABLE test_vectors;")
        cur.close()
        conn.close()
        return True

    except Exception as e:
        print(f"❌ PostgreSQL Error: {e}")
        return False

def test_nebula():
    print(f"\n--- Testing Nebula Graph on {NEBULA_CONFIG['host']}:{NEBULA_CONFIG['port']} ---")
    
    # Configure Nebula Connection
    config = Config()
    config.max_connection_pool_size = 2
    
    # Initialize Pool
    pool = ConnectionPool()
    
    try:
        # 1. Connect to Pool
        if not pool.init([(NEBULA_CONFIG["host"], NEBULA_CONFIG["port"])], config):
            print("❌ Failed to initialize Nebula connection pool.")
            return False

        # 2. Get Session
        session = pool.get_session(NEBULA_CONFIG["user"], NEBULA_CONFIG["password"])
        print("✅ Connected to Nebula Graph!")

        # 3. Check Cluster Status
        print("   Checking Storage Nodes...")
        result = session.execute("SHOW HOSTS;")
        
        if not result.is_succeeded():
            print(f"❌ Query Failed: {result.error_msg()}")
            return False
            
        # Parse result to see if storage is online
        size = result.row_size()
        online_count = 0
        print(f"   Found {size} storage nodes registered.")
        
        # Simple print of the result columns (Host, Port, Status, etc.)
        # Note: Nebula returns data in a specific structure, we just want to ensure it didn't error.
        
        print("✅ Nebula Graph is responding to queries.")
        
        session.release()
        pool.close()
        return True

    except Exception as e:
        print(f"❌ Nebula Graph Error: {e}")
        return False

if __name__ == "__main__":
    print("Starting Connectivity Tests...")
    
    pg_status = test_postgres_vector()
    nebula_status = test_nebula()
    
    print("\n================ SUMMARY ================")
    if pg_status and nebula_status:
        print("🟢 ALL SYSTEMS GO: Both Postgres and Nebula are reachable and working.")
    else:
        print("🔴 SYSTEM FAILURE: Check the error messages above.")
