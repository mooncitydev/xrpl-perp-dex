# Hack the Block Париж — план на 36 часов

**Команда:** Alex, Andrey, Tom
**Трек:** Challenge 2 — Impact Finance
**Проект:** Perp DEX на XRPL через Intel SGX (TEE)

---

## Что уже готово (НЕ делаем на хакатоне)

Всё ниже **live и проверено** на 10 апреля 2026:

- Live API: `api-perp.ph18.io` (nginx, TLS, CORS)
- SGX margin engine (C/C++ enclave) с DCAP attestation на 3 Azure DCsv3 нодах
- Rust orchestrator: CLOB orderbook, P2P gossipsub, sequencer election (split-brain протестирован)
- 2-of-3 multisig withdrawal через XRPL нативный SignerListSet — **работает в Rust**, проверен на testnet настоящими ECDSA подписями из SGX enclave
- WebSocket с Fill/OrderUpdate/PositionChanged + channel subscriptions
- PostgreSQL репликация трейдов между 3 операторами (B3.1)
- Persistence resting orders + failover recovery (C5.1)
- 16/16 E2E тестов проходят, 9/9 сценариев отказов с 10 on-chain tx proof
- Готовый пакет заявки на грант + proof-of-traction

**Стратегия: мы НЕ строим DEX на хакатоне. Он готов. Мы строим ДЕМО-СЛОЙ и ИНТЕГРАЦИИ, от которых судьи скажут "это настоящее".**

---

## Таймлайн 36 часов

### Часы 0-2: Настройка и выравнивание (все 3)

- [ ] Подключиться к WiFi площадки, протестить SSH до Hetzner + Azure
- [ ] Проверить что `api-perp.ph18.io` отвечает с сети площадки
- [ ] Smoke test: `curl markets`, `wscat wss://api-perp.ph18.io/ws`
- [ ] Проверить DCAP attestation на Azure node-2 (4734-byte quote)
- [ ] Договориться о разделении задач (ниже) и зафиксировать deliverables

### Часы 2-14: Спринт (параллельные треки)

**Трек A — Фронтенд торговый UI (Tom, ~12ч)**

Собрать минимальный но красивый веб-UI на `perp.ph18.io`:
- [ ] Подключение кошелька (XRPL через GemWallet или Crossmark расширение)
- [ ] Отображение live mark price + funding rate из REST API
- [ ] Стакан (bids/asks) из REST + WebSocket обновления
- [ ] Отправка limit/market ордеров через auth REST (подпись кошельком)
- [ ] Показ открытых ордеров + позиций (polling /v1/orders, /v1/account/balance)
- [ ] Real-time fills через WebSocket `user:rXXX` channel subscription
- [ ] Кнопка "Verify Enclave" → вызывает `/v1/attestation/quote` → показывает MRENCLAVE + размер quote

**Стек:** React или Next.js, Tailwind CSS, лёгкий. Бэкенд не нужен — чистый API клиент. API CORS-ready.

**Минимум для демо:** цена + отправка ордера + see fills live. Кнопка "verify enclave" — это wow-фактор.

**Трек B — Настройка live trading демо (Andrey, ~4ч)**

- [ ] Пополнить 2 тестовых кошелька на XRPL testnet
- [ ] Deposit RLUSD (или XRP) в escrow account для обоих
- [ ] Разместить начальные maker ордера на реалистичных ценах (spread вокруг Binance mid)
- [ ] Написать простого маркет-мейкер бота (Python цикл: quote bid/ask вокруг Binance цены каждые 5 сек)
  - 50 строк Python с `tools/xrpl_auth.py` для подписи
  - Создаёт ликвидность чтобы демо выглядело живым
- [ ] Протестить полный flow: deposit → maker quote → taker crosses → WS shows fill → withdraw multisig
- [ ] Записать backup asciinema на случай проблем с интернетом

**Трек C — Страница верификации attestation + питч (Alex, ~6ч)**

- [ ] Собрать standalone страницу: `verify.ph18.io`
  - Вход: вставить DCAP quote hex (или кликнуть "fetch from live node")
  - Выход: разобранные поля quote (MRENCLAVE, MRSIGNER, CPUSVN, PCK chain)
  - Сравнить MRENCLAVE с хешем опубликованного `enclave.signed.so`
  - Показать "✅ Enclave запускает опубликованный код" или "❌ Несовпадение"
  - Можно статичный HTML + JS, без бэкенда
- [ ] Отполировать 5-минутный питч для судей:
  - Проблема → Решение → Почему XRPL → Live демо → Attestation proof → Призыв
  - Прогнать 2 раза с таймером
- [ ] Подготовить Q&A шпаргалку (топ-10 вопросов + 1-строчные ответы)
- [ ] Подготовить 1-страничное summary проекта для нетворкинга

### Часы 14-18: Интеграция и полировка (все 3)

- [ ] Подключить фронтенд к live API — end-to-end тест из UI
- [ ] Пофиксить CSS/UX баги что Tom нашёл
- [ ] Andrey — маркет-мейкер бот поддерживает книгу
- [ ] Alex — проверить верификатор attestation на live Azure quote
- [ ] Прогнать полный демо-flow вместе:
  1. Открыть `perp.ph18.io` → живые цены
  2. Подключить кошелёк
  3. Отправить limit order → видно в стакане
  4. Crossing order с другого кошелька → fill на WebSocket
  5. Кликнуть "Verify Enclave" → DCAP quote → MRENCLAVE совпадает
  6. Withdraw через multisig → показать tx на XRPL testnet explorer
- [ ] Если время: записать 2-минутное видео-прохождение как backup

### Часы 18-24: Сон + буфер

Будем реалистами — 6 часов сна. Не пропускать.

### Часы 24-30: Финальная полировка

- [ ] Пофиксить баги найденные после отдыха
- [ ] Tom полирует UI (responsive, error states, loading spinners)
- [ ] Andrey проверяет инфру: Azure VMs живы, тоннели up, orchestrator OK
- [ ] Alex финализирует слайды, порядок соответствует демо-flow
- [ ] Прогнать демо 2 раза (3-мин и 5-мин версии)
- [ ] Подготовить offline backup: скриншоты, записанное демо, заготовленные tx hashes

### Часы 30-34: Подготовка к демо

- [ ] Сабмитить проект на платформу хакатона (описание, ссылки, команда)
- [ ] Подготовить демо-лэптоп: табы открыты, кошельки подключены, терминал ready
- [ ] Последний smoke test с площадки
- [ ] Быстрый huddle: кто что презентует, кто отвечает на технические вопросы
- [ ] Alex: вступление + проблема + решение (2 мин)
- [ ] Tom: live демо walkthrough (2 мин)
- [ ] Andrey: attestation proof + архитектура если спросят (1 мин + Q&A)

### Часы 34-36: Презентации и судейство

- [ ] Презентовать
- [ ] Нетворкинг с судьями
- [ ] Собрать контакты заинтересованных (VC, другие команды, XRPL folk)

---

## Чего НЕ делать на хакатоне

1. **Не переписывать orchestrator** — он работает, 16/16 E2E passing
2. **Не трогать SGX enclave** — цикл rebuild длинный и ошибкоопасный
3. **Не добавлять новые торговые фичи** (типы ордеров, рынки) — scope creep
4. **Не оптимизировать производительность** — latency достаточная для демо
5. **Не пытаться mainnet launch** — testnet безопаснее для live демо

## Критерии судейства (типично для Impact Finance)

По опыту прошлых хакатонов:
- **Техническое исполнение** (40%) — работает ли? можете показать live?
- **Инновационность** (25%) — это ново для XRPL экосистемы?
- **Потенциал влияния** (20%) — кому это полезно и насколько?
- **Качество презентации** (15%) — чётко, уверенно, в тайминг

Наши сильные стороны:
- Техническое исполнение — наш главный козырь. У нас РАБОТАЮЩИЙ продукт, не прототип
- Инновационность — TEE подход к DeFi на chain без смарт-контрактов — уникален
- Влияние: RLUSD utility story + институциональный DeFi на XRPL
- Презентация: нужна полировка (Трек C)

---

## Аварийный набор (если что-то сломается)

| Проблема | Решение |
|---|---|
| Azure VMs отключились | `az vm start -g SGX-RG -n sgx-node-{1,2,3}` с Hetzner |
| Hetzner orchestrator умер | `cd /tmp/perp-9088 && bash start script` |
| SSH тоннели упали | Пересоздать: `ssh -f -N -L 9188:localhost:9088 azureuser@20.71.184.176` |
| XRPL testnet faucet лежит | Использовать заранее пополненные кошельки (сохранить seeds) |
| WiFi площадки блокирует SSH | Хотспот телефона как fallback |
| Live демо сломалось на сцене | Переключиться на записанное backup видео |

---

## Ключевые цифры для питча

- **$280M** — потери Drift Protocol (апрель 2026, social engineering на human multisig)
- **4,734 байт** — размер нашего Intel-подписанного DCAP attestation quote
- **16.5 секунд** — failover sequencer (протестировано live)
- **3 секунды** — reconvergence после split-brain (протестировано live)
- **10** — on-chain XRPL testnet транзакций доказывающих 9/9 сценариев отказов
- **12 транзакций** — всего верифицированных multisig tx на testnet
- **16/16** — E2E test pass rate (проверено сегодня)
- **$150K** — сумма заявки на грант (пакет готов)
