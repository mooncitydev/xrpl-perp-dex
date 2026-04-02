# TEE vs Smart Contract: почему нас нельзя ограбить как Drift

**Дата:** 2026-04-02
**Контекст:** Drift Protocol (Solana perp DEX) потерял $200M+ из-за компрометации приватного ключа администратора

---

## Что произошло с Drift

1. Атакующий получил доступ к **приватному ключу admin signer**
2. Подготовился: профондировал кошельки за неделю, сделал тестовую транзакцию
3. Одним батчем транзакций вывел **всё**: SOL, WETH, BTC, стейблкоины
4. Конвертировал в USDC, bridged в Ethereum
5. Протокол опубликовал "unusual activity" когда было уже поздно

**Корневая причина:** один приватный ключ контролировал все средства. Кто имеет ключ — тот имеет всё.

---

## Почему это невозможно в нашей архитектуре

### 1. Ключ не существует вне SGX

```
Drift:                           Наша архитектура:
┌──────────┐                     ┌──────────────────┐
│ Admin key│ ← хранится          │ SGX Enclave      │
│ в файле/ │    где-то           │ ┌──────────────┐ │
│ в HSM/   │    доступном        │ │ ECDSA Key A  │ │
│ в памяти │    оператору        │ │ (sealed,     │ │
└──────────┘                     │ │  never leaves│ │
     │                           │ │  enclave)    │ │
     │ украден →                 │ └──────────────┘ │
     │ полный доступ             └──────────────────┘
     ▼                                    │
  $200M вывод                     Оператор НЕ МОЖЕТ
                                  извлечь ключ
```

В SGX приватный ключ **генерируется внутри enclave** и **никогда не покидает** его. Оператор запускает enclave, но физически не может прочитать содержимое enclave memory — это гарантия на уровне процессора Intel.

### 2. Multisig 2-of-3 — нет единого ключа

```
Drift: 1 admin key → полный контроль

Наша архитектура:
  Operator A (Azure): ECDSA Key A — внутри SGX
  Operator B (Azure): ECDSA Key B — внутри SGX
  Operator C (Azure): ECDSA Key C — внутри SGX

  XRPL Escrow: SignerListSet [A, B, C], quorum=2
  Master key: DISABLED

  Для любого withdrawal нужно 2 из 3 подписей.
  Каждый ключ внутри своего SGX enclave.
  Операторы на разных серверах, разных провайдерах.
```

Даже если атакующий **полностью скомпрометирует** один сервер (root доступ, физический доступ) — он получит доступ только к одному enclave. Для вывода средств нужно скомпрометировать **два enclave на двух разных серверах**.

### 3. Enclave код определяет правила — оператор не может их обойти

```
Drift: admin key может делать что угодно
       (перевести все средства на свой адрес)

Наша архитектура:
  Enclave код (attested, open-source):
    - Withdrawal только после margin check
    - Signing только для конкретного user + amount
    - Rate limit на withdrawals
    - Spending guardrails (signature count limit)

  Оператор НЕ МОЖЕТ заставить enclave подписать
  произвольную транзакцию — код enclave это запрещает.
```

### 4. DCAP Attestation — код верифицирован

```
Drift: пользователи доверяют что smart contract делает
       то что написано (но admin key обходит всё)

Наша архитектура:
  1. Enclave публикует MRENCLAVE (хеш кода)
  2. Intel подписывает SGX Quote (DCAP)
  3. Любой может верифицировать:
     - Код enclave = опубликованный open-source код
     - Работает на настоящем Intel SGX
     - Оператор не модифицировал код

  Если оператор попытается запустить модифицированный
  enclave — MRENCLAVE изменится → attestation провалится
  → пользователи увидят подмену
```

### 5. XRPL Settlement — средства на L1, не в контракте

```
Drift: все средства внутри smart contract на Solana
       admin key = полный доступ к контракту = полный доступ к средствам

Наша архитектура:
  Средства: RLUSD на XRPL escrow account
  Контроль: SignerListSet 2-of-3 (не smart contract)

  XRPL — фиксированный протокол, нет upgradeable contracts.
  SignerListSet — нативная фича XRPL, не наш код.
  Нет admin key, нет upgrade function, нет proxy pattern.
```

---

## Сравнительная таблица атак

| Вектор атаки | Drift (Smart Contract) | Наша архитектура (TEE + Multisig) |
|---|---|---|
| **Кража admin key** | ✅ Полный доступ ($200M) | ❌ Нет admin key. Ключи в SGX, multisig 2-of-3 |
| **Insider threat** | ✅ Один человек с ключом | ❌ Нужен сговор 2 из 3 операторов + SGX compromise |
| **Social engineering** | ✅ Убедить хранителя ключа | ❌ Ключ нельзя "показать" — он в hardware |
| **Phishing** | ✅ Подписать фейковую tx | ❌ Enclave проверяет что tx валидна (margin check) |
| **Supply chain attack** | ✅ Подменить contract upgrade | ❌ MRENCLAVE изменится → attestation fail |
| **Rehearsal attack** | ✅ Тестовая tx → ждать → drain | ❌ Каждая tx проходит margin check в enclave |
| **Rug pull** | ✅ Admin выводит всё | ❌ Master key disabled, SignerListSet неизменяем без multisig |

---

## Что если SGX скомпрометирован?

Теоретические side-channel атаки на SGX существуют (Spectre, Foreshadow). Но:

1. **Один скомпрометированный SGX = один ключ** из трёх. Для вывода нужно 2.
2. **Key rotation:** при обнаружении уязвимости — новые ключи, новый SignerListSet, перевод средств.
3. **Intel microcode updates:** исправляют известные side-channels.
4. **Временное окно:** атакующему нужно скомпрометировать 2 SGX одновременно, до key rotation.

Сравните: в Drift ключ украден один раз — **навсегда**. В нашей архитектуре — даже если один SGX скомпрометирован, у нас есть время на key rotation.

---

## Что если оператор — злоумышленник?

| Действие оператора | Drift | Наша архитектура |
|---|---|---|
| Вывести все средства | ✅ Один tx (admin key) | ❌ Нужно 2-of-3 + enclave подпишет только valid tx |
| Подменить код | ✅ Upgrade contract | ❌ MRENCLAVE изменится → DCAP attestation fail |
| Задержать withdrawals | ✅ Pause contract | ⚠️ Может задержать если он sequencer, но 2 других оператора продолжат |
| Front-run пользователей | ✅ MEV (видит все tx) | ❌ Orders зашифрованы для enclave |
| Подделать цены | ✅ Modify oracle | ⚠️ Медиана от 3 операторов, один не может повлиять |

---

## Практические рекомендации

### Для пользователей нашего DEX:

1. **Проверьте attestation** перед депозитом: `POST /v1/attestation/quote` → верифицируйте MRENCLAVE
2. **Проверьте SignerListSet** на XRPL: убедитесь что escrow имеет quorum=2, master disabled
3. **Убедитесь что операторы на разных провайдерах** (Azure, OVH, Hetzner)
4. **Следите за key rotation** — если MRENCLAVE изменился, проверьте почему

### Для операторов:

1. **Никогда не храните ключи вне SGX** — все ключи генерируются внутри enclave
2. **Disable master key** на escrow account — всегда
3. **Мониторинг:** alerting на нетипичные withdrawals, spending limit guardrails
4. **Регулярный key rotation** — не ждите инцидента
5. **DCAP attestation** — публикуйте MRENCLAVE, дайте пользователям верифицировать

---

## Итог

| | Drift (до взлома) | Наша архитектура |
|---|---|---|
| Модель безопасности | Один admin key | TEE + Multisig 2-of-3 |
| Минимум для кражи | 1 ключ | 2 SGX compromise + 2 operator collusion |
| Время на реакцию | 0 (одна tx) | Есть (key rotation, 2-of-3 продолжает работать) |
| Верификация кода | Audit отчёт (статический) | DCAP attestation (runtime, Intel-signed) |
| Средства | В smart contract (admin control) | На XRPL L1 (SignerListSet, no admin) |
| Recovery | Невозможно (средства ушли) | Key rotation + новый escrow + перевод средств |

**$200M Drift hack невозможен в TEE + Multisig архитектуре.**
Не потому что мы умнее — а потому что **ключ физически недоступен** оператору.
