# Data pipeline

## Cadence

The ingestion cadence is 15 minutes. Each gateway posts a batch of readings.

## Deduplication

The dedupe key is device id plus timestamp. A repeated key is dropped, not merged.

## Storage

Readings land in Postgres first. The reporting tables refresh every hour.

## Failure handling

A failed batch is retried 3 times with exponential backoff. After the third failure the batch goes to a dead-letter table.
