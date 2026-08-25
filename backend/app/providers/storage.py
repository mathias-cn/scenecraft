from app.config import settings


def upload_media(*, job_id: str, source: str) -> str:
    """Envia o arquivo para S3 ou Cloudflare R2. Sem credenciais, ecoa o source."""
    configured = settings.s3_access_key_id and settings.s3_bucket
    looks_real = configured and not settings.s3_access_key_id.startswith("your_")
    if not looks_real:
        return source if source.startswith("http") else f"stub://storage/{job_id}.mp4"

    import boto3

    client_kwargs: dict = {
        "aws_access_key_id": settings.s3_access_key_id,
        "aws_secret_access_key": settings.s3_secret_access_key,
        "region_name": settings.s3_region,
    }
    endpoint = settings.object_storage_endpoint
    if endpoint:
        client_kwargs["endpoint_url"] = endpoint

    s3 = boto3.client("s3", **client_kwargs)
    key = f"videos/{job_id}.mp4"
    # source ainda é um URL/placeholder neste scaffold; o worker futuro fará upload binário.
    s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=source.encode("utf-8"))

    if settings.r2_public_base_url:
        return f"{settings.r2_public_base_url.rstrip('/')}/{key}"
    return f"s3://{settings.s3_bucket}/{key}"
