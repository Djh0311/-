"""Write-trapping synthetic flow objects.

The fixtures are intentionally generated in memory and contain no copied source
material.  Read counters make the addon's capability boundary observable.
"""

from collections import Counter


ALLOWED_JSON_KEYS = frozenset(
    (
        "a",
        "account",
        "active",
        "address",
        "b",
        "catalog",
        "count",
        "email",
        "field",
        "id",
        "items",
        "label",
        "name",
        "note",
        "number",
        "phone",
        "price",
        "store",
        "tags",
        "x",
        "y",
        "z",
    )
)

SENSITIVE_SCHEMA_KEY_VARIANTS = (
    "APIKEY",
    "USERID",
    "DEVICEID",
    "RECIPIENTPHONE",
    "api2Key",
    "user2Id",
    "device2Id",
    "recipient2Phone",
    "apiKeys",
    "api_keys",
    "api-keys",
    "userIds",
    "userIDs",
    "deviceIds",
    "deviceIDs",
    "recipientPhones",
    "accessTokens",
    "clientSecrets",
    "apiSecrets",
    "sessions",
    "passwords",
    "accountIds",
    "idCards",
    "personalEmails",
    "deliveryAddresses",
    "verificationCodes",
    "smsCodes",
    "openIds",
    "unionIds",
    "merchantAPIKey",
    "merchantTokenLabel",
    "userIdV2",
    "userId2",
    "apiKey2",
    "deviceIdHash",
    "recipientPhoneMasked",
    "apiV2Key",
    "api_v2_key",
    "APIV2KEY",
    "userV2Id",
    "user_v2_id",
    "USERV2ID",
    "deviceV2Id",
    "device_v2_id",
    "DEVICEV2ID",
    "recipientPrimaryPhone",
    "personalBackupEmail",
    "apiSigningKey",
    "userExternalId",
    "userLegacyId",
    "deviceAdvertisingId",
    "deviceHardwareId",
    "recipientContactPhone",
    "personalPrimaryEmail",
    "deliveryStreetAddress",
    "verificationOtpCode",
    "smsOtpCode",
    "accountExternalId",
    "openPlatformId",
    "userUID",
    "deviceUUID",
    "recipientTel",
    "otpCode",
    "privateKey",
    "awsAccessKeyId",
    "pwd",
    "sessId",
    "oauthCode",
    "uid",
    "uuid",
    "guid",
)


class SyntheticCancellation(BaseException):
    """A cancellation-shaped failure carrying data the addon must not expose."""


class ManualClock:
    def __init__(self, initial=100.0):
        self._value = float(initial)

    def __call__(self):
        return self._value

    def advance(self, seconds):
        self._value += float(seconds)


class _WriteTrap:
    def _finish_initialization(self):
        object.__setattr__(self, "_initialized", True)

    def __setattr__(self, name, value):
        if getattr(self, "_initialized", False):
            tracker = object.__getattribute__(self, "_tracker")
            tracker["flow_mutations"] += 1
            raise AssertionError("FLOW_MUTATION_FORBIDDEN")
        object.__setattr__(self, name, value)


class GuardedRequest(_WriteTrap):
    def __init__(self, tracker, method, host, path):
        object.__setattr__(self, "_tracker", tracker)
        object.__setattr__(self, "_method", method)
        object.__setattr__(self, "_host", host)
        object.__setattr__(self, "_path", path)
        self._finish_initialization()

    @property
    def method(self):
        self._tracker["request_method_reads"] += 1
        return self._method

    @property
    def host(self):
        self._tracker["request_host_reads"] += 1
        return self._host

    @property
    def path(self):
        self._tracker["request_path_reads"] += 1
        return self._path

    def _forbidden_read(self, field):
        self._tracker["request_" + field + "_reads"] += 1
        self._tracker["forbidden_request_reads"] += 1
        raise AssertionError("FORBIDDEN_REQUEST_READ")

    @property
    def query(self):
        return self._forbidden_read("query")

    @property
    def url(self):
        return self._forbidden_read("url")

    @property
    def headers(self):
        return self._forbidden_read("headers")

    @property
    def body(self):
        return self._forbidden_read("body")

    @property
    def content(self):
        return self._forbidden_read("content")

    @property
    def raw_content(self):
        return self._forbidden_read("raw_content")

    @property
    def path_components(self):
        return self._forbidden_read("path_components")

    def __getattr__(self, name):
        self._tracker["request_unknown_reads"] += 1
        self._tracker["forbidden_request_reads"] += 1
        raise AssertionError("FORBIDDEN_REQUEST_READ")


class GuardedHeaders(_WriteTrap):
    _ALLOWED = frozenset(("content-type", "content-length", "content-encoding"))

    def __init__(self, tracker, values, after_read=None):
        object.__setattr__(self, "_tracker", tracker)
        normalized = {}
        for key, value in values.items():
            normalized[str(key).lower()] = value
        object.__setattr__(self, "_values", normalized)
        object.__setattr__(self, "_after_read", after_read)
        self._finish_initialization()

    def get(self, name, default=None):
        normalized = str(name).lower()
        if normalized not in self._ALLOWED:
            self._tracker["forbidden_response_header_reads"] += 1
            raise AssertionError("FORBIDDEN_RESPONSE_HEADER_READ")
        self._tracker["response_header_" + normalized] += 1
        result = self._values.get(normalized, default)
        callback = self._after_read
        if callback is not None:
            callback(normalized)
        return result

    def __iter__(self):
        self._tracker["forbidden_response_header_reads"] += 1
        raise AssertionError("RESPONSE_HEADER_ITERATION_FORBIDDEN")

    def __getattr__(self, name):
        self._tracker["forbidden_response_header_reads"] += 1
        raise AssertionError("FORBIDDEN_RESPONSE_HEADER_READ")


class GuardedResponse(_WriteTrap):
    def __init__(
        self,
        tracker,
        body,
        status_code=200,
        content_type="application/json",
        content_length=None,
        content_encoding=None,
        read_failure=None,
        before_body_read=None,
        after_header_read=None,
    ):
        object.__setattr__(self, "_tracker", tracker)
        object.__setattr__(self, "_body", body)
        object.__setattr__(self, "_status_code", status_code)
        object.__setattr__(self, "_read_failure", read_failure)
        object.__setattr__(self, "_before_body_read", before_body_read)
        headers = {"content-type": content_type}
        if content_length is not None:
            headers["content-length"] = content_length
        if content_encoding is not None:
            headers["content-encoding"] = content_encoding
        object.__setattr__(
            self,
            "_headers",
            GuardedHeaders(tracker, headers, after_read=after_header_read),
        )
        self._finish_initialization()

    @property
    def status_code(self):
        self._tracker["response_status_reads"] += 1
        return self._status_code

    @property
    def headers(self):
        self._tracker["response_headers_object_reads"] += 1
        return self._headers

    @property
    def raw_content(self):
        self._tracker["response_body_reads"] += 1
        callback = self._before_body_read
        if callback is not None:
            callback()
        failure = self._read_failure
        if failure is not None:
            raise failure
        return self._body

    def __getattr__(self, name):
        self._tracker["forbidden_response_reads"] += 1
        raise AssertionError("FORBIDDEN_RESPONSE_READ")


class GuardedFlow(_WriteTrap):
    def __init__(self, request, response, tracker):
        object.__setattr__(self, "_tracker", tracker)
        object.__setattr__(self, "_request", request)
        object.__setattr__(self, "_response", response)
        self._finish_initialization()

    @property
    def request(self):
        self._tracker["request_object_reads"] += 1
        return self._request

    @property
    def response(self):
        self._tracker["response_object_reads"] += 1
        return self._response

    def __getattr__(self, name):
        self._tracker["forbidden_flow_reads"] += 1
        raise AssertionError("FORBIDDEN_FLOW_READ")


def synthetic_flow(
    body,
    method="GET",
    host="api.synthetic.invalid",
    path="/v1/discovery",
    status_code=200,
    content_type="application/json",
    content_length=None,
    content_encoding=None,
    read_failure=None,
    before_body_read=None,
    after_header_read=None,
):
    tracker = Counter()
    request = GuardedRequest(tracker, method, host, path)
    response = GuardedResponse(
        tracker,
        body,
        status_code=status_code,
        content_type=content_type,
        content_length=content_length,
        content_encoding=content_encoding,
        read_failure=read_failure,
        before_body_read=before_body_read,
        after_header_read=after_header_read,
    )
    return GuardedFlow(request, response, tracker), tracker


def generated_sensitive_marker():
    """Return a synthetic canary without storing its contiguous form in source."""

    return "".join(("SYNTHETIC", "_PRIVATE", "_CANARY"))
