#!/usr/bin/env python3
"""
Script to generate an encryption key for CONFIG_ENCRYPTION_KEY
"""
from cryptography.fernet import Fernet

def generate_key():
    """Generate a new Fernet encryption key"""
    key = Fernet.generate_key()
    print("="*60)
    print("GENERATED ENCRYPTION KEY")
    print("="*60)
    print(f"CONFIG_ENCRYPTION_KEY={key.decode()}")
    print("="*60)
    print("Add this line to your .env file:")
    print(f"echo 'CONFIG_ENCRYPTION_KEY={key.decode()}' >> secrets/config_encryption_key.txt")
    print("="*60)
    print("⚠️  IMPORTANT: Keep this key secure and backed up!")
    print("⚠️  If you lose this key, all encrypted data will be unrecoverable!")
    print("="*60)

if __name__ == "__main__":
    try:
        generate_key()
    except ImportError:
        print("Error: cryptography package not installed")
        print("Install it with: pip install cryptography")
