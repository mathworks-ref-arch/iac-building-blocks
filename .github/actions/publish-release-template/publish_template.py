# Copyright 2026 The MathWorks, Inc.
"""Publish a release template to a fixed S3 key.

Creates the key if it doesn't exist, otherwise replaces the current object
unless a newer run of the same repository wrote it. Both writes are
conditional, so an object that changes while this runs is never overwritten.
The run id and repository are stored as object metadata for later runs to
compare against. Emits the template URL, the version id and the result as
GitHub Actions outputs.
"""
import argparse
import hashlib
import os
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError

RUN_ID_KEY = 'github-run-id'
REPOSITORY_KEY = 'github-repository'


class PublishError(Exception):
    """A condition that must stop the publish, with a message for the log."""


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--template-file', required=True)
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--acl', default='public-read', help="Canned ACL, empty for none")
    parser.add_argument('--region', default='us-east-1', help="Region of the bucket")
    return parser.parse_args()


def is_precondition_failed(error):
    """True if a ClientError is S3's answer to a failed If-Match or If-None-Match."""
    response = error.response
    return (response.get('Error', {}).get('Code') == 'PreconditionFailed'
            or response.get('ResponseMetadata', {}).get('HTTPStatusCode') == 412)


def newer_writer(metadata, repository, run_id):
    """Return the run id that wrote the object if it is a newer run of this repository, else None."""
    if metadata.get(REPOSITORY_KEY) != repository:
        return None
    try:
        writer = int(metadata.get(RUN_ID_KEY, ''))
    except ValueError:
        return None
    return writer if writer > run_id else None


def publish(s3, body, bucket, key, acl, repository, run_id):
    """Write the template and return (result, version_id), result being 'created' or 'replaced'."""
    put_args = {
        'Bucket': bucket,
        'Key': key,
        'Body': body,
        'ContentType': 'application/json',
        'Metadata': {RUN_ID_KEY: str(run_id), REPOSITORY_KEY: repository},
    }
    if acl:
        put_args['ACL'] = acl

    try:
        response = s3.put_object(IfNoneMatch='*', **put_args)
        return 'created', response.get('VersionId', '')
    except ClientError as e:
        if not is_precondition_failed(e):
            raise

    current = s3.head_object(Bucket=bucket, Key=key)
    newer = newer_writer(current.get('Metadata', {}), repository, run_id)
    if newer is not None:
        raise PublishError(f"s3://{bucket}/{key} was written by newer run {newer}; not overwriting")

    try:
        response = s3.put_object(IfMatch=current['ETag'], **put_args)
    except ClientError as e:
        if is_precondition_failed(e):
            raise PublishError(f"s3://{bucket}/{key} changed while publishing; not overwriting") from e
        raise
    return 'replaced', response.get('VersionId', '')


def verify(s3, bucket, key, md5, run_id):
    """Check that the object now in S3 is the one this run wrote."""
    current = s3.head_object(Bucket=bucket, Key=key)
    etag = current['ETag'].strip('"')
    if etag != md5:
        raise PublishError(f"s3://{bucket}/{key} has ETag {etag}, expected {md5}")
    writer = current.get('Metadata', {}).get(RUN_ID_KEY)
    if writer != str(run_id):
        raise PublishError(f"s3://{bucket}/{key} was written by run {writer}, expected {run_id}")


def write_outputs(template_url, version_id, result):
    """Write the action outputs to the GitHub Actions output file."""
    with open(os.environ['GITHUB_OUTPUT'], 'a') as fh:
        fh.write(f"template_url={template_url}\n")
        fh.write(f"version_id={version_id}\n")
        fh.write(f"result={result}\n")


def main():
    args = get_args()
    with open(args.template_file, 'rb') as fh:
        body = fh.read()
    md5 = hashlib.md5(body, usedforsecurity=False).hexdigest()
    run_id = int(os.environ['GITHUB_RUN_ID'])
    repository = os.environ['GITHUB_REPOSITORY']
    template_url = f"https://{args.bucket}.s3.amazonaws.com/{args.key}"

    s3 = boto3.client('s3', region_name=args.region)
    try:
        result, version_id = publish(s3, body, args.bucket, args.key, args.acl, repository, run_id)
        verify(s3, args.bucket, args.key, md5, run_id)
    except PublishError as e:
        print(f"::error::{e}")
        sys.exit(1)
    except (BotoCoreError, ClientError) as e:
        print(f"::error::Failed to publish {args.template_file} to s3://{args.bucket}/{args.key}: {e}")
        sys.exit(1)

    print(f"Template {result}: {template_url}" + (f" (version {version_id})" if version_id else ""))
    write_outputs(template_url, version_id, result)


if __name__ == "__main__":
    main()
