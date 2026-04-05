from automation.catalog.definitions import ConnectionTypeDefinition, IntegrationApp, ParameterDefinition, ParameterOptionDefinition


WEBHOOK_BASIC_AUTH_CONNECTION = ConnectionTypeDefinition(
    id="webhook.basic_auth",
    integration_id="webhook",
    label="Basic Auth",
    auth_kind="http_secret",
    description="Reusable Basic Auth credential for inbound webhooks.",
    field_schema=(
        ParameterDefinition(
            key="username",
            label="Username",
            value_type="string",
            required=True,
            description="Username expected on incoming webhook requests.",
            placeholder="admin",
        ),
        ParameterDefinition(
            key="password",
            label="Password",
            value_type="secret_ref",
            required=True,
            description="Password expected on incoming webhook requests.",
            placeholder="password",
        ),
    ),
)


WEBHOOK_HEADER_AUTH_CONNECTION = ConnectionTypeDefinition(
    id="webhook.header_auth",
    integration_id="webhook",
    label="Header Auth",
    auth_kind="http_secret",
    description="Reusable Header Auth credential for inbound webhooks.",
    field_schema=(
        ParameterDefinition(
            key="name",
            label="Name",
            value_type="string",
            required=True,
            description="Header name to validate on incoming webhook requests.",
            default="X-Webhook-Secret",
            placeholder="X-Webhook-Secret",
        ),
        ParameterDefinition(
            key="value",
            label="Value",
            value_type="secret_ref",
            required=True,
            description="Header value expected on incoming webhook requests.",
            placeholder="secret",
        ),
    ),
)


WEBHOOK_SHARED_SECRET_CONNECTION = ConnectionTypeDefinition(
    id="webhook.shared_secret",
    integration_id="webhook",
    label="Header Auth",
    auth_kind="http_secret",
    description="Legacy reusable Header Auth credential for inbound webhooks.",
    field_schema=(
        ParameterDefinition(
            key="header_name",
            label="Name",
            value_type="string",
            required=True,
            description="Header name to validate on incoming webhook requests.",
            default="X-Webhook-Secret",
            placeholder="X-Webhook-Secret",
        ),
        ParameterDefinition(
            key="secret_value",
            label="Value",
            value_type="secret_ref",
            required=True,
            description="Header value expected on incoming webhook requests.",
            placeholder="secret",
        ),
    ),
)


WEBHOOK_JWT_AUTH_CONNECTION = ConnectionTypeDefinition(
    id="webhook.jwt_auth",
    integration_id="webhook",
    label="JWT Auth",
    auth_kind="http_secret",
    description="Reusable JWT Auth credential for inbound webhooks.",
    field_schema=(
        ParameterDefinition(
            key="key_type",
            label="Key Type",
            value_type="string",
            required=True,
            description="Choose either the secret passphrase or PEM encoded public key.",
            default="passphrase",
            options=(
                ParameterOptionDefinition(value="passphrase", label="Passphrase"),
                ParameterOptionDefinition(value="pemKey", label="PEM Key"),
            ),
        ),
        ParameterDefinition(
            key="secret",
            label="Secret",
            value_type="secret_ref",
            required=False,
            description="Secret used to verify JWT signatures for passphrase-based tokens.",
            placeholder="secret",
        ),
        ParameterDefinition(
            key="public_key",
            label="Public Key",
            value_type="secret_ref",
            required=False,
            description="PEM encoded public key used to verify JWT signatures.",
            placeholder="-----BEGIN PUBLIC KEY-----",
        ),
        ParameterDefinition(
            key="algorithm",
            label="Algorithm",
            value_type="string",
            required=True,
            description="Algorithm used to verify the JWT signature.",
            default="HS256",
            options=(
                ParameterOptionDefinition(value="HS256", label="HS256"),
                ParameterOptionDefinition(value="HS384", label="HS384"),
                ParameterOptionDefinition(value="HS512", label="HS512"),
                ParameterOptionDefinition(value="RS256", label="RS256"),
                ParameterOptionDefinition(value="RS384", label="RS384"),
                ParameterOptionDefinition(value="RS512", label="RS512"),
                ParameterOptionDefinition(value="ES256", label="ES256"),
                ParameterOptionDefinition(value="ES384", label="ES384"),
                ParameterOptionDefinition(value="ES512", label="ES512"),
                ParameterOptionDefinition(value="PS256", label="PS256"),
                ParameterOptionDefinition(value="PS384", label="PS384"),
                ParameterOptionDefinition(value="PS512", label="PS512"),
                ParameterOptionDefinition(value="none", label="none"),
            ),
        ),
    ),
)


APP = IntegrationApp(
    id="webhook",
    label="Webhook",
    description="Reusable webhook credentials.",
    icon="mdi-webhook",
    category_tags=("webhook", "http"),
    connection_types=(
        WEBHOOK_BASIC_AUTH_CONNECTION,
        WEBHOOK_HEADER_AUTH_CONNECTION,
        WEBHOOK_JWT_AUTH_CONNECTION,
        WEBHOOK_SHARED_SECRET_CONNECTION,
    ),
    actions=(),
    triggers=(),
    sort_order=10,
)
