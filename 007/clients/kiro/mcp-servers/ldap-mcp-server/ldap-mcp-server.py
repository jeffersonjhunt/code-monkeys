#!/usr/bin/env python3
"""LDAP MCP Server — exposes LDAP directory search/read over MCP stdio."""

import os

from ldap3 import Connection, Server, ALL, SUBTREE
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ldap-directory")

LDAP_URI = os.environ.get("LDAP_URI", "ldap://localhost:389")
LDAP_BIND_DN = os.environ.get("LDAP_BIND_DN", "")
LDAP_BIND_PASSWORD = os.environ.get("LDAP_BIND_PASSWORD", "")
LDAP_BASE_DN = os.environ.get("LDAP_BASE_DN", "dc=example,dc=com")
LDAP_USE_SSL = os.environ.get("LDAP_USE_SSL", "false").lower() == "true"


def _connect() -> Connection:
    server = Server(LDAP_URI, get_info=ALL, use_ssl=LDAP_USE_SSL)
    conn = Connection(server, user=LDAP_BIND_DN or None, password=LDAP_BIND_PASSWORD or None, auto_bind=True)
    return conn


@mcp.tool()
def search(filter: str, base_dn: str = "", attributes: str = "*", size_limit: int = 50) -> str:
    """Search LDAP directory with an LDAP filter expression.

    Args:
        filter: LDAP filter string, e.g. '(uid=jsmith)' or '(&(objectClass=person)(cn=*hunt*))'
        base_dn: Base DN to search from (defaults to LDAP_BASE_DN env var)
        attributes: Comma-separated attribute list or '*' for all
        size_limit: Max entries to return
    """
    conn = _connect()
    try:
        search_base = base_dn or LDAP_BASE_DN
        attr_list = [a.strip() for a in attributes.split(",")] if attributes != "*" else ["*"]
        conn.search(search_base, filter, search_scope=SUBTREE, attributes=attr_list, size_limit=size_limit)
        results = []
        for entry in conn.entries:
            results.append(f"dn: {entry.entry_dn}\n{entry.entry_to_ldif()}")
        return "\n---\n".join(results) if results else "No entries found."
    finally:
        conn.unbind()


@mcp.tool()
def read_entry(dn: str, attributes: str = "*") -> str:
    """Read a specific LDAP entry by its distinguished name.

    Args:
        dn: The full distinguished name of the entry
        attributes: Comma-separated attribute list or '*' for all
    """
    conn = _connect()
    try:
        attr_list = [a.strip() for a in attributes.split(",")] if attributes != "*" else ["*"]
        conn.search(dn, "(objectClass=*)", search_scope="BASE", attributes=attr_list)
        if conn.entries:
            entry = conn.entries[0]
            return f"dn: {entry.entry_dn}\n{entry.entry_to_ldif()}"
        return f"Entry not found: {dn}"
    finally:
        conn.unbind()


@mcp.tool()
def list_children(base_dn: str = "", attributes: str = "cn,ou,objectClass") -> str:
    """List immediate children of a base DN (one-level search).

    Args:
        base_dn: Parent DN (defaults to LDAP_BASE_DN env var)
        attributes: Comma-separated attribute list
    """
    conn = _connect()
    try:
        search_base = base_dn or LDAP_BASE_DN
        attr_list = [a.strip() for a in attributes.split(",")]
        conn.search(search_base, "(objectClass=*)", search_scope="LEVEL", attributes=attr_list)
        results = []
        for entry in conn.entries:
            results.append(f"dn: {entry.entry_dn}\n{entry.entry_to_ldif()}")
        return "\n---\n".join(results) if results else "No children found."
    finally:
        conn.unbind()


if __name__ == "__main__":
    mcp.run(transport="stdio")
