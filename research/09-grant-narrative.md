# Заявка на грант: Perpetual Futures DEX на XRPL

**Проект:** TEE-защищённый DEX бессрочных фьючерсов с расчётами в RLUSD
**Команда:** ph18.io
**Дата:** 2026-04-07
**Статус:** Черновик — ожидаем форму гранта

---

## Проблема

XRPL не поддерживает смарт-контракты. Это делает невозможным создание сложных DeFi
протоколов — бессрочные фьючерсы, опционы, кредитование — напрямую на леджере. Проекты
либо уходят на сайдчейны (теряя гарантии безопасности XRPL), либо строят
централизованные сервисы (теряя trustless свойства).

У RLUSD, регулируемого стейблкоина Ripple, нет DeFi-экосистемы на XRPL mainnet.
Пользователи RLUSD не могут использовать его для yield farming или хеджирования —
единственный вариант это мосты на Ethereum или Solana.

---

## Решение

Мы заменяем смарт-контракты на **Trusted Execution Environments (Intel SGX)**. Анклав
выполняет ту же логику что и смарт-контракт — margin engine, трекинг позиций,
подпись withdrawal — но с аппаратной защитой целостности. XRPL используется для того,
в чём он лучший: расчёты.

```
User → nginx (TLS) → Orchestrator (Rust) → SGX Enclave (C/C++)
                                                  │
                                                  ▼
                                            XRPL Mainnet
                                         (расчёты в RLUSD)
```

### Почему TEE вместо смарт-контрактов?

| Смарт-контракты (Solidity, Move) | TEE (Intel SGX) |
|----------------------------------|-----------------|
| Требуют поддержки на уровне блокчейна | Работает с любым блокчейном, включая XRPL |
| Код публичен (MEV, front-running) | Код выполняется в зашифрованной памяти |
| Газ за каждую операцию | Нет газа — вычисления бесплатны |
| Обновления требуют governance | Обновления требуют attestation |
| Уязвимы к re-entrancy, flash loans | Поверхность атаки — аппаратная (side-channel), не логика |

### Почему XRPL?

- **RLUSD** — регулируемый стейблкоин, институциональное доверие
- **3-4 секунды** финальность — достаточно для торговли
- **Нативный multisig** (SignerListSet) — не нужен смарт-контракт для 2-of-3 custody
- **Низкие комиссии** — < $0.001 за транзакцию
- **Нет MEV** — у XRPL нет фронтраннинга мемпула

---

## Что построено

### Работающий PoC (live: api-perp.ph18.io)

| Компонент | Технология | Статус |
|-----------|-----------|--------|
| **Margin engine** | C/C++ внутри SGX enclave | ✅ Live |
| **Order book** | Rust CLOB с price-time priority | ✅ Live |
| **Price feed** | Binance XRP/USDT, обновление каждые 5 сек | ✅ Live |
| **Аутентификация** | Верификация подписей XRPL secp256k1 | ✅ Live |
| **Мониторинг депозитов** | Отслеживание escrow на XRPL | ✅ Live |
| **Подпись withdrawal** | Enclave проверяет margin + ECDSA подпись | ✅ Live |
| **WebSocket** | Real-time trades, orderbook, ticker, liquidations | ✅ Live |
| **DCAP attestation** | Intel SGX Quote v3 на Azure DCsv3 | ✅ Верифицировано |
| **Multi-operator P2P** | libp2p gossipsub, выбор sequencer | ✅ Реализовано |
| **State commitment** | TEE-подписанный Merkle root на Sepolia | ✅ Реализовано |

### Уникальные свойства безопасности

1. **Безопасность withdrawal:** Enclave проверяет маржу перед подписью. Даже при
   компрометации оператора, анклав отказывает в подписи если withdrawal оставит
   позиции недостаточно обеспеченными.

2. **Мульти-операторный custody:** XRPL нативный multisig (SignerListSet 2-of-3).
   Три независимых оператора на разных серверах. Нет единой точки отказа.

3. **Верифицируемые вычисления:** DCAP remote attestation доказывает что анклав
   запускает подлинный, немодифицированный код. Любой может проверить.

4. **Защита от атак типа Drift:** В отличие от Solidity DEX (Drift потерял $280M),
   TEE подход исключает flash loan атаки, re-entrancy и манипуляцию governance.

---

## Этапы и майлстоуны

### Milestone 1: PoC (✅ Завершён)
- SGX enclave с полным margin engine
- Rust orchestrator с CLOB orderbook
- XRPL deposit/withdrawal на testnet
- DCAP remote attestation на Azure DCsv3
- 111 автоматизированных тестов
- Live API: https://api-perp.ph18.io

### Milestone 2: Мультиоператорный testnet (Неделя 1-4)
- 3 оператора (Azure DCsv3)
- XRPL mainnet multisig (SignerListSet 2-of-3)
- State commitment на Ethereum mainnet
- Интеграция с фронтендом (perp.ph18.io)

### Milestone 3: Mainnet beta (Неделя 5-8)
- Расчёты в RLUSD на mainnet
- Публичная верификация DCAP attestation
- SDK для сторонней интеграции
- Аудит безопасности (enclave + orchestrator)

### Milestone 4: Production launch (Неделя 9-12)
- Vault система (ликвидация, HLP, delta-0, delta-1)
- XRP стейкинг с тирами комиссий
- Дополнительные рынки (ETH-RLUSD-PERP)
- Оптимизация производительности

---

## Открытый исходный код

- **Код:** BSL 1.1 — конвертируется в Apache 2.0 через 4 года
- **Исследования:** CC BY-NC-ND 4.0
- **Репозитории:**
  - `xrpl-perp-dex` — Orchestrator (Rust), research docs, API guide
  - `xrpl-perp-dex-enclave` — SGX enclave (C/C++), perp engine
