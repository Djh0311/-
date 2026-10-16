"""Bounded TLS failure metadata; never inspect error text or certificates."""

import ipaddress
import re


_HOSTNAME = re.compile(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\Z")
_VERIFY_REASONS = {
    "TLS_VERIFY_EXPIRED": ("X509_V_ERR_CERT_HAS_EXPIRED",),
    "TLS_VERIFY_NOT_YET_VALID": ("X509_V_ERR_CERT_NOT_YET_VALID",),
    "TLS_VERIFY_NAME_MISMATCH": (
        "X509_V_ERR_HOSTNAME_MISMATCH", "X509_V_ERR_IP_ADDRESS_MISMATCH"),
    "TLS_VERIFY_UNTRUSTED": (
        "X509_V_ERR_UNABLE_TO_GET_ISSUER_CERT",
        "X509_V_ERR_UNABLE_TO_GET_ISSUER_CERT_LOCALLY",
        "X509_V_ERR_DEPTH_ZERO_SELF_SIGNED_CERT",
        "X509_V_ERR_SELF_SIGNED_CERT_IN_CHAIN",
        "X509_V_ERR_UNABLE_TO_VERIFY_LEAF_SIGNATURE",
        "X509_V_ERR_CERT_UNTRUSTED", "X509_V_ERR_INVALID_CA"),
}


def _verification_status(connection):
    if connection is None:
        return "TLS_VERIFY_UNKNOWN"
    try:
        # This is the structured OpenSSL verification result, not conn.error.
        # Keep this dependency optional for preparation/offline tests.
        from OpenSSL import SSL
        value = SSL._lib.SSL_get_verify_result(connection._ssl)
        if type(value) is not int or value < 0:
            return "TLS_VERIFY_UNKNOWN"
        if value == 0:
            # A zero verification error does NOT mean the handshake succeeded.
            return "TLS_VERIFY_NO_ERROR_REPORTED"
        for reason, names in _VERIFY_REASONS.items():
            if any(value == getattr(SSL._lib, name, None) for name in names):
                return reason
        return "TLS_VERIFY_OTHER"
    except Exception:
        return "TLS_VERIFY_UNKNOWN"


def _name(value):
    if value is None:
        return "ABSENT", None
    if type(value) is not str or len(value) > 253:
        return "UNKNOWN", None
    if value == "":
        return "ABSENT", None
    try:
        return "IP", ipaddress.ip_address(value).compressed
    except ValueError:
        labels = value.rstrip(".").split(".")
        if all(_HOSTNAME.fullmatch(label) for label in labels):
            return "HOSTNAME", value.rstrip(".").lower()
        return "UNKNOWN", None


def _transport_state(connection):
    """Snapshot engine flags, not a diagnosis of who closed or why."""
    try:
        from mitmproxy.connection import ConnectionState
        state = connection.state
        if type(state) is ConnectionState:
            for name in ("CLOSED", "CAN_READ", "CAN_WRITE", "OPEN"):
                if state is getattr(ConnectionState, name):
                    return name
    except Exception:
        pass
    return "UNKNOWN"


def upstream_tls_failure_metadata(data):
    """Reduce engine names and verification result to a fixed closed object."""
    result = {
        "schema_version": "p26-upstream-tls-failure/v1",
        "verification_status": "TLS_VERIFY_UNKNOWN",
        "upstream_name_kind": "UNKNOWN",
        "client_name_kind": "UNKNOWN",
        "upstream_name_matches_client": None,
        "upstream_transport_state": "UNKNOWN",
        "client_transport_state": "UNKNOWN",
    }
    try:
        result["upstream_transport_state"] = _transport_state(data.conn)
    except Exception:
        pass
    try:
        result["client_transport_state"] = _transport_state(data.context.client)
    except Exception:
        pass
    try:
        upstream_kind, upstream = _name(data.conn.sni)
        client_kind, client = _name(data.context.client.sni)
        result.update(upstream_name_kind=upstream_kind, client_name_kind=client_kind)
        if upstream is not None and client is not None:
            result["upstream_name_matches_client"] = (
                upstream_kind == client_kind and upstream == client)
    except Exception:
        pass
    try:
        result["verification_status"] = _verification_status(data.ssl_conn)
    except Exception:
        pass
    return result
