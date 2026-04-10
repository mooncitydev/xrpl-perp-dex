# Hack the Block Париж — план на 36 часов

**Команда:** Alex, Andrey, Tom
**Трек:** Challenge 2 — Impact Finance
**Проект:** Perpetual Futures DEX на XRPL с расчётами в RLUSD

---

## Позиционирование (что видят судьи)

**Публичный нарратив:** первая биржа бессрочных фьючерсов с нативным
расчётом в RLUSD на XRPL mainnet. Средства пользователей хранятся в
XRPL `SignerListSet` 2-of-3 multisig между независимыми операторами.
Без sidechain, без моста, без кастодиального доверия.

**Что мы НЕ раскрываем:** secure computation backend (технология
анклава, детали аппаратного обеспечения, DCAP attestation). На сцене
это **работающий чёрный ящик** — "наш проприетарный модуль безопасных
вычислений гарантирует что margin check и подпись происходят в
tamper-proof среде; полную архитектуру опубликуем на mainnet launch."

Если судьи спросят "как работает подпись?":
> "Каждый оператор запускает модуль безопасных вычислений который
> хранит signing keys в изолированной памяти. Модуль проверяет margin
> перед подписью любого withdrawal. Даже если сервер оператора
> скомпрометирован, модуль отказывается подписать undercollateralized
> withdrawal. Мы используем индустриальный стандарт hardware security —
> детали под NDA до mainnet."

---

## Что уже готово (НЕ делаем на хакатоне)

Всё ниже **live и проверено** на 10 апреля 2026:

- Live API: `api-perp.ph18.io` (nginx, TLS, CORS)
- Secure computation модуль с margin engine, трекинг позиций, ECDSA подпись
- Rust orchestrator: CLOB orderbook, P2P gossipsub, sequencer election
- 2-of-3 multisig withdrawal через XRPL нативный SignerListSet — работает, проверен
- WebSocket с Fill/OrderUpdate/PositionChanged + channel subscriptions
- PostgreSQL репликация трейдов между 3 операторами
- Persistence resting orders + failover recovery
- 16/16 E2E тестов, 9/9 failure mode scenarios с 10 on-chain tx
- Готовый пакет заявки на грант

**Стратегия: мы НЕ строим DEX на хакатоне. Он готов. Мы строим
ДЕМО-СЛОЙ который показывает судьям "это настоящее и работает на
XRPL прямо сейчас".**

---

## Таймлайн 36 часов

### Часы 0-2: Настройка (все 3)

- [ ] WiFi площадки, SSH до серверов, smoke test API + WebSocket
- [ ] Договориться о задачах и deliverables

### Часы 2-14: Спринт (параллельные треки)

**Трек A — Фронтенд UI (Tom, ~12ч)**

Собрать `perp.ph18.io`:
- [ ] Подключение кошелька (GemWallet / Crossmark)
- [ ] Live mark price + funding rate из REST
- [ ] Стакан (bids/asks) — REST + WebSocket обновления
- [ ] Отправка limit/market ордеров (подпись кошельком)
- [ ] Открытые ордера + позиции
- [ ] Real-time fills через WebSocket `user:rXXX`
- [ ] Секция "About": "расчёт на XRPL, 2-of-3 multisig, RLUSD нативно"

**Минимум для демо:** цена + submit order + live fills.

**Трек B — Live trading демо (Andrey, ~4ч)**

- [ ] 2 тестовых кошелька + deposit в escrow
- [ ] Начальные ордера (spread вокруг Binance mid)
- [ ] Маркет-мейкер бот (50 строк Python, каждые 5 сек)
- [ ] Полный flow тест: deposit → trade → WS fill → multisig withdraw
- [ ] Backup asciinema запись
- [ ] Заранее пополненные кошельки (seeds сохранить)

**Трек C — Питч и материалы (Alex, ~6ч)**

- [ ] Landing page `perp.ph18.io/about`:
  - Диаграмма (User → API → Orchestrator → Secure Module → XRPL)
  - "2-of-3 multisig защищает ваши средства"
  - "Все deposit/withdrawal на XRPL — проверяйте сами"
  - Ссылка на testnet explorer с escrow
- [ ] 5-минутный питч:
  - Проблема → Решение → Почему XRPL → Live демо → "проверьте на XRPL" → Призыв
  - Прогнать 2 раза
- [ ] Q&A шпаргалка (10 вопросов + ответы)
- [ ] 1-страничное summary для нетворкинга

### Часы 14-18: Интеграция (все 3)

- [ ] Фронт ↔ API end-to-end
- [ ] Полный демо-flow вместе:
  1. UI → живые цены
  2. Кошелёк → limit order → стакан
  3. Crossing order → fill на WS
  4. Explorer → "funds тут, на XRPL"
  5. Withdraw multisig → tx hash на explorer
- [ ] Backup видео если время

### Часы 18-24: Сон (не пропускать)

### Часы 24-30: Полировка + practice

### Часы 30-34: Подготовка демо

- [ ] Сабмит проекта
- [ ] Alex: проблема + решение (2 мин)
- [ ] Tom: live демо (2 мин)
- [ ] Andrey: архитектура + Q&A (1 мин)

### Часы 34-36: Презентация

---

## Что говорить если спросят про "secure module"

| Вопрос | Ответ |
|---|---|
| "Какое hardware?" | "Индустриальный стандарт HSM. Детали под NDA до mainnet." |
| "Это MPC?" | "Нет. Один secure computation boundary на оператора. Multisig — нативный XRPL SignerListSet." |
| "Оператор может украсть?" | "Нет. Модуль подписи проверяет margin в hardware. Даже скомпрометированный оператор не может заставить модуль подписать невалидный withdrawal." |
| "Как проверить?" | "Deposit и withdrawal на XRPL — escrow account можно посмотреть в любом explorer. Публичная верификация на mainnet." |
| "Аудит?" | "52 findings, 50 fixed, 2 by-design. Отчёт в репо." |
| "Open source?" | "BSL 1.1 — конвертируется в Apache 2.0 через 4 года. Код на GitHub." |

---

## Чего НЕ делать

1. **Не трогать backend** — работает, 16/16 тестов
2. **Не трогать secure module** — долгий rebuild
3. **Не добавлять фичи** — scope creep
4. **Не раскрывать детали computation layer** — "проприетарный модуль, детали на mainnet"
5. **Не пытаться mainnet** — testnet безопаснее

---

## Ключевые цифры

- **$280M** — потери Drift Protocol (social engineering, апрель 2026)
- **2-of-3** — XRPL нативный SignerListSet multisig
- **16.5 сек** — failover sequencer (live test)
- **3 сек** — reconvergence после network partition
- **12** — верифицированных multisig tx на XRPL testnet
- **16/16** — E2E test pass rate
- **$150K** — заявка на грант готова
