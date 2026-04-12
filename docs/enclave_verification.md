# SGX Enclave Verification

## MRENCLAVE

```
48dc7f6ce749077653d7dac1597016b20f4e4c08cbec859973adbd8f2575a09b
```

This is the SHA-256 hash of the code running inside the SGX enclave, computed by the CPU during enclave loading. It can be verified via remote attestation at [xperp.fi/verify](https://xperp.fi/verify).

## Enclave Binary

The signed enclave binary (`enclave.signed.so`) is published in the root of this repository.

File hash (SHA-256):
```
30cf9331311775e7a930051fb4bd37838b9e0eb1033377e7c20e971a1b418d95  enclave.signed.so
```

## How to Verify

1. Verify the file hash:
```bash
sha256sum enclave.signed.so
# Expected: 30cf9331311775e7a930051fb4bd37838b9e0eb1033377e7c20e971a1b418d95
```

2. Extract MRENCLAVE from the binary (requires Intel SGX SDK):
```bash
sgx_sign dump -enclave enclave.signed.so -dumpfile /dev/stdout 2>/dev/null \
  | grep -A2 'enclave_hash.m' \
  | tail -2 \
  | tr -d ' ' \
  | sed 's/0x//g' \
  | tr -d '\n'
# Expected: 48dc7f6ce749077653d7dac1597016b20f4e4c08cbec859973adbd8f2575a09b
```

3. Compare the extracted MRENCLAVE with the value returned by remote attestation at [xperp.fi/verify](https://xperp.fi/verify).

If they match, the enclave is running authentic, unmodified code.
