"""Record the EC2 public IPv4 from IMDSv2 for LDL's Compose and Nginx."""
from ipaddress import IPv4Address
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener


def public_ipv4():
    metadata = "http://169.254.169.254/latest"
    client = build_opener(ProxyHandler({}))
    token_request = Request(f"{metadata}/api/token", method="PUT", headers={
        "X-aws-ec2-metadata-token-ttl-seconds": "60",
    })
    with client.open(token_request, timeout=3) as response:
        token = response.read(4096).decode("ascii")
    address_request = Request(f"{metadata}/meta-data/public-ipv4", headers={
        "X-aws-ec2-metadata-token": token,
    })
    with client.open(address_request, timeout=3) as response:
        address = IPv4Address(response.read(64).decode("ascii").strip())
    if not address.is_global:
        raise ValueError("EC2 public IPv4 required")
    return address


def save(path, value, mode):
    if path.exists() and path.read_text() == value:
        return
    with NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(value)
            output.close()
            temporary.chmod(mode)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def write_config(directory, address):
    hosts = directory / "hosts"
    hosts.mkdir(parents=True, exist_ok=True)
    hosts.chmod(0o755)
    save(hosts / "public-ip.conf", f"{address} 1;\n", 0o644)
    save(directory / "public-ip.env", f"GUIDED_EC2_PUBLIC_IP={address}\n", 0o600)


def main():
    try:
        address = public_ipv4()
        write_config(Path(sys.argv[1]), address)
    except (URLError, OSError, ValueError):
        print("EC2 공인 IPv4를 확인할 수 없습니다. 인스턴스의 공인 IPv4와 IMDSv2 설정을 확인하세요.", file=sys.stderr)
        return 1
    print(address)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
