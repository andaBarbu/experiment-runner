# Domain-Specific Usage Examples

Experiment Runner is designed to be domain-agnostic. Below are practical examples demonstrating how it can be configured and used across different research domains.

These examples are meant to help researchers quickly adapt the framework to their own experimental setup.

## 1. Code-level Performance Measurements
This experiment compares the performance of two implementations of summation under different input sizes.

### Set-Up
- Factors:
  - algorithm ∈ {sum_loop, optimized_sum}
  - input_size ∈ {10k, 100k, 500k}
- Metric:
  - execution_time_ms

