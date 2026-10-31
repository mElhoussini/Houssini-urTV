#!/usr/bin/env python3
"""Make the apps' signing key once, on your own computer, for the repository's secrets.

The key signs both APKs; Android only installs an update signed with the same key, so keep the file and the
password it prints somewhere safe (a password manager). It is written to your home folder, outside the repo, and
must never be committed.

  pip install cryptography
  python .github/tools/make_signing_key.py

With GitHub CLI installed and signed in (`gh auth login`), it stores both secrets in the verified `origin`
repository and prints nothing secret. Without it, it keeps the key local and exits without printing the secrets.
The builds sign with it from then on (CI refuses to build without it). TVs that have apps signed with another
key need them installed again once (optimize/install.sh does that by itself; their settings start over).
"""
import base64
import datetime
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

ALIAS = b"urtv"   # android/*/build.gradle signs with this alias


def make(password):
    key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "UrTV"), x509.NameAttribute(NameOID.ORGANIZATION_NAME, "UrTV")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=365 * 100))   # Android wants it valid long after the last update
            .sign(key, hashes.SHA256()))
    return pkcs12.serialize_key_and_certificates(ALIAS, key, cert, None,
                                                 serialization.BestAvailableEncryption(password.encode()))


def main():
    out = Path.home() / "urtv-signing-key.p12"
    password_file = Path.home() / "urtv-signing-key-password.txt"
    if out.exists() or password_file.exists():
        if not out.is_file() or not password_file.is_file():
            sys.exit("Only one signing-key file exists; keep it safe and restore its pair before continuing.")
        data = out.read_bytes()
        password = password_file.read_text().rstrip("\n")
        print(f"Reusing your existing key at {out}; password file at {password_file}.")
    else:
        password = secrets.token_urlsafe(30)
        data = make(password)
        write_private(out, data)
        write_private(password_file, (password + "\n").encode())
        print(f"Key saved to {out}, its password to {password_file}.")
        print("Back up both securely; never commit them.\n")
    out.chmod(0o600)
    password_file.chmod(0o600)
    secret = {"ANDROID_KEYSTORE_B64": base64.b64encode(data).decode(), "ANDROID_KEYSTORE_PASSWORD": password}
    gh = gh_ready()
    if gh:
        repo = github_repo(gh)
        if not repo:
            sys.exit("Could not verify that origin is your GitHub repository. No secrets were changed.")
        for name, value in secret.items():   # the value goes in on stdin, never on the command line
            subprocess.run([gh, "secret", "set", name, "--repo", repo], input=value, text=True, check=True)
        print(f"Both secrets are now in {repo}. The next build signs with this key.")
        return
    sys.exit(f"GitHub CLI isn't signed in. No secrets were changed. Run `gh auth login`, then rerun this script; your key remains at {out}.")


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def gh_ready():
    """GitHub CLI's path if it is installed and signed in, else None."""
    gh = shutil.which("gh")
    return gh if gh and subprocess.run([gh, "auth", "status"], capture_output=True).returncode == 0 else None


def github_repo(gh):
    """Use and verify origin explicitly, so an upstream remote cannot receive this key."""
    remote = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True)
    if remote.returncode != 0:
        return None
    match = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", remote.stdout.strip())
    if not match:
        return None
    repo = match.group(1)
    user = subprocess.run([gh, "api", "user", "--jq", ".login"], capture_output=True, text=True)
    if user.returncode != 0 or repo.split("/", 1)[0].casefold() != user.stdout.strip().casefold():
        return None
    result = subprocess.run([gh, "repo", "view", repo, "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
                            capture_output=True, text=True)
    return repo if result.returncode == 0 and result.stdout.strip().casefold() == repo.casefold() else None


if __name__ == "__main__":
    main()
