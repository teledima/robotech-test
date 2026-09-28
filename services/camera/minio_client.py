from minio import Minio


class MinioClient(Minio):
    def __init__(
            self,
            endpoint,
            access_key = None,
            secret_key = None,
            session_token = None,
            secure = True,
            region = None,
            http_client = None,
            credentials = None,
            cert_check = True,
        ):
        super().__init__(
            endpoint,
            access_key,
            secret_key,
            session_token,
            secure,
            region,
            http_client,
            credentials,
            cert_check,
        )
        self._endpoint = endpoint

    def s3_public_url(self, bucket_name: str, object_name: str) -> str:
        return f'http://{self._endpoint}/{bucket_name}/{object_name}'
