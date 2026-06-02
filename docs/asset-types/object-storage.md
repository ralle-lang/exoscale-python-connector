# object-storage bucket

S3-compatible object storage. **This is the one asset type that does NOT
use the APIv2.** Buckets are managed via the S3 API at
`https://sos-<zone>.exo.io` using `boto3` and S3 SigV4 — the same
`EXOSCALE_API_KEY` / `EXOSCALE_API_SECRET` are used as the
`aws_access_key_id` / `aws_secret_access_key`. The connector wraps boto3
behind an asset-type interface that matches the other types.

## Install

Object Storage support is an optional extra:

```bash
pip install 'exoscale-connector[sos]'
```

`boto3` is **lazily imported** inside the bucket client, so the rest of the
connector works without it installed.

## Model

```python
class Bucket(ExoscaleModel):
    name: Optional[str]            # globally unique across all of S3
    creation_date: Optional[str]
```

## CLI

```bash
exoscale-bucket list
exoscale-bucket exists --name my-bucket-name
exoscale-bucket create --name my-bucket-name
exoscale-bucket delete --name my-bucket-name
```

## Library

```python
from exoscale_connector import ClientConfig
from exoscale_connector.resources.object_storage import BucketClient

# BucketClient takes a ClientConfig (not an ExoscaleClient) because it
# builds its own boto3 S3 client internally.
config = ClientConfig.from_env(zone="de-fra-1")
buckets = BucketClient(config)

buckets.create("my-unique-bucket-name-1234")
assert buckets.exists("my-unique-bucket-name-1234")
for b in buckets.list():
    print(b.name, b.creation_date)
buckets.delete("my-unique-bucket-name-1234")
```

For test injection, pass a pre-built S3 client:

```python
buckets = BucketClient(config, s3_client=my_mock_s3_client)
```

## Gotchas

- **Bucket names are globally unique across all of S3**, not just your
  account — pick a long, unique name (3–63 chars, lowercase, no
  underscores). The live test uses a random 16-char suffix.
- **`delete_bucket` fails if the bucket is non-empty.** The connector
  exposes the raw S3 delete; if you need recursive cleanup, do it via
  boto3 directly before calling `buckets.delete()`.
- **Different endpoint per zone:** `https://sos-<zone>.exo.io`. The
  connector derives this from the zone in your `ClientConfig`.
- **Not behind `ExoscaleClient`.** The signed-session and operation-polling
  in `ExoscaleClient` are APIv2-specific; boto3 brings its own retry,
  pagination and error handling.
- **One key spans both surfaces — if the IAM role allows SOS.** The
  connector hands the same `EXOSCALE_API_KEY` / `EXOSCALE_API_SECRET` to
  both APIv2 and S3/SOS, and a single key works for both — *verified against
  a live tenant* whose role grants the `sos` service (`list_buckets`
  succeeded with the same key used for APIv2). The catch is the role: if it
  omits object-storage, `list_buckets` and friends fail with an opaque S3
  access-denied even though the same key works fine on APIv2. Grant it in
  the policy's `services` map (see the
  [IAM policy cookbook](../iam-policy-cookbook.md)).

## End-to-end example

Distilled from
[`tests/integration/test_tier_2.py::test_bucket_lifecycle`](../../tests/integration/test_tier_2.py):

```python
import secrets, string
from exoscale_connector import ClientConfig
from exoscale_connector.resources.object_storage import BucketClient

config = ClientConfig.from_env(zone="de-fra-1")
buckets = BucketClient(config)

suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(16))
name = f"smoke-test-{suffix}"

buckets.create(name)
assert buckets.exists(name)
assert any(b.name == name for b in buckets.list())
buckets.delete(name)
assert not buckets.exists(name)
```
