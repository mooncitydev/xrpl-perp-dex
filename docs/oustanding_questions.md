# Questions to be answered:

1. How to actually run the orchestrator?

```bash
# create a config file as so?

cd orachestrator
make run
```

2. Price is got from the enclave endpoint.
- How is the price calculated? It should be an oracle price, is this implemented? 

3. We are using a custom type for the prices, whhich poorly simulates decimal numbers. We should use a better type, such as `rust_decimal` or `bigdecimal`. (rust decimal is much faster).

4. What exactly is the purpose of the orchestrator? Is it to hold the book or just to integrate with the enclave? 
Afaik, the oorders are submitted to the enclave, so where is the exactly the book held? Is it in the enclave or in the orchestrator? If it's in the enclave, then what is the purpose of the orchestrator? Simply to act as an api gateway?

5. TradingEngine does 2 things, it both holds the book and submits state to be syncronised with the enclave. How is the book syncronised with the enclave? Does the enclave send the updated book to the orchestrator after processing an order? Or does the orchestrator request the updated book from the enclave after processing an order?


## Ordering issue and questions.

1. Wen thhis is deployed as market of distributed system, what is the ordering of a sent order. 
- User sends order to orchestrator
- Orchestrator sends order to enclave
- Enclave processes order and updates book?
- Enclave sends updated book to orchestrator?
- Enclave sends updated book to OTHER orchestrators?

What happens if 2 orders are sent at the same time to 2 different orchestrators? How is the ordering of these 2 orders determined? Is it just the order in which they are received by the enclave? What if enclave 1 receives order A first and enclave 2 receives order B first, but order B is actually sent before order A?

How is ordering determined in this system? Is it just the first enclave to receive the order? What if there are multiple enclaves? How is the ordering of orders determined across multiple enclaves?

## Endpoints needed in orchestrator

1. positions/get: give me the positions i have in the market, and the details of those positions (size, entry price, etc)
2. funding/rates/get: give me the current funding rates for the markets
3. funding/payments/get: give me the funding payments i have made/received

## Correctness and Verifiability

1. openapi spec should be used to generate the models used, at present this is NOT how it is done, the models and the open api spec are completely seperate. Will cause drift and incompatibilities. We should use the spec in build.rs to generate the models used in the orchestrator, this will ensure that the models are always up to date with the spec and that there are no incompatibilities between the models and the spec.
2. We should have a test suite that tests the correctness of the system, by sending orders to the orchestrator and checking the state of the book after processing those orders. This will ensure that the system is working correctly and that the book is being updated correctly after processing orders.
3. https://github.com/77ph/xrpl-perp-dex/blob/master/DEPLOYMENT.md#what-is-exposed-externally-via-nginx This is massively out of date referencing endpoints which dont exist anymore, and not referencing endpoints which do exist. This should be updated to reflect the current state of the system, and should be kept up to date as the system evolves. This will ensure that users of the system have accurate information about what endpoints are available and how to use them.