# CQKD DHT Scaling Tests

This directory contains the comprehensive test suite for validating the CQKD DHT scaling implementation.

## Overview

The scaling test suite validates all four major corrections implemented:

1. ✅ **Dynamic Ports System** (Range 7000-8000)
2. ✅ **Adaptive Kademlia Parameters** (ALPHA/K/timeout dinamici)
3. ✅ **Hierarchical Health Check System** (3 livelli)
4. ✅ **Multi-Node Bootstrap** (6 nodes con load balancing)

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.8+
- Required Python packages: `matplotlib seaborn pandas`

### Running Tests

#### Quick Test (Small & Medium only)
```bash
./scripts/run_scaling_tests.sh -q
```

#### Full Test Suite (All scenarios)
```bash
./scripts/run_scaling_tests.sh
```

#### Dry Run (Validation only)
```bash
./scripts/run_scaling_tests.sh --dry-run
```

#### Cleanup Only
```bash
./scripts/run_scaling_tests.sh -c
```

## Test Scenarios

| Scenario | Workers | Bootstrap Nodes | Duration | Purpose |
|----------|----------|-----------------|----------|---------|
| Small    | 15       | 2               | 15 min   | Baseline validation |
| Medium   | 50       | 3               | 25 min   | First threshold |
| Large    | 100      | 4               | 35 min   | Second threshold |
| XLarge   | 200      | 6               | 50 min   | Third threshold |
| XXLarge  | 500      | 6               | 75 min   | Stress test |

## Target Metrics

| Metric | Target | Small | Medium | Large | XLarge | XXLarge |
|--------|--------|-------|--------|-------|--------|---------|
| Bootstrap Time | <120s | 30s | 60s | 90s | 120s | 120s |
| Discovery Success Rate | >95% | 95% | 95% | 95% | 95% | 95% |
| Network Health Score | >0.7 | 0.7 | 0.7 | 0.7 | 0.7 | 0.7 |
| Port Conflicts | 0 | 0 | 0 | 0 | 0 | 0 |
| Health Check Effectiveness | >90% | 90% | 90% | 90% | 90% | 90% |

## File Structure

```
├── test_scaling_validation.py    # Main Python test suite
├── scripts/
│   └── run_scaling_tests.sh     # Bash automation script
├── test_results/               # Test output directory
│   ├── scaling_test_*.log      # Test logs
│   ├── result_*.json           # Test results
│   ├── metrics_*.json         # Performance metrics
│   └── *.png                  # Performance graphs
└── docs/
    └── scaling_test_report.md   # Detailed test report
```

## Test Components

### 1. Dynamic Ports Validation

Tests the automatic port allocation system:
- Verifies unique port assignment for each worker
- Checks port range compliance (7000-8000)
- Detects port conflicts
- Validates port distribution efficiency

### 2. Adaptive Kademlia Parameters

Validates parameter adaptation based on network size:
- ALPHA parameter scaling (3 → 8)
- K parameter scaling (20 → 40)
- Timeout adaptation (5s → 12s)
- Network category detection

### 3. Health Check System

Tests the hierarchical health check implementation:
- Fast checks (1-3s timeout)
- Medium checks (2-4.5s timeout)
- Deep checks (5-7.5s timeout)
- Batch processing efficiency
- Node removal effectiveness

### 4. Bootstrap System

Validates multi-node bootstrap with load balancing:
- Bootstrap node selection strategies
- Load distribution across nodes
- Worker-to-bootstrap ratios
- Fallback mechanisms

### 5. CQKD Protocol Integration

Tests Alice/Bob protocol integration:
- API reachability (localhost:8001, localhost:8002)
- Key exchange functionality
- Protocol stability under load

## Interpreting Results

### Success Criteria

A test scenario passes when:
- ✅ Bootstrap time ≤ target
- ✅ Discovery success rate ≥ 95%
- ✅ Network health score ≥ 0.7
- ✅ Zero port conflicts
- ✅ Health check effectiveness ≥ 90%

### Warning Indicators

⚠️ **Warnings** indicate potential issues:
- Bootstrap time approaching limits
- Success rate dropping below 97%
- Network health score declining
- Resource usage spikes

### Failure Indicators

❌ **Failures** require immediate attention:
- Bootstrap timeout
- Success rate < 95%
- Network health score < 0.7
- Port conflicts detected
- Health check effectiveness < 90%

## Performance Graphs

The test suite generates several performance graphs:

### 1. Bootstrap Time Scaling
Shows how bootstrap time increases with worker count
- **Expected:** Linear scaling within targets
- **Concern:** Exponential growth or timeouts

### 2. Success Rate by Scale
Bar chart showing discovery success rates
- **Expected:** >95% across all scales
- **Concern:** Rates dropping below target

### 3. Resource Usage Trends
CPU and memory usage across scales
- **Expected:** Linear growth
- **Concern:** Unexpected spikes or plateaus

### 4. Network Health Score
Network health metrics over time
- **Expected:** Stable >0.7 scores
- **Concern:** Declining health scores

## Troubleshooting

### Common Issues

#### Docker Build Failures
```bash
# Clean and rebuild
docker system prune -f
docker-compose down --remove-orphans
./scripts/run_scaling_tests.sh -s -c
```

#### Port Conflicts
```bash
# Check for port conflicts
netstat -tuln | grep 7000-8000
# Clean up containers
docker-compose down --remove-orphans
```

#### Test Timeouts
```bash
# Increase timeouts or run quick test
./scripts/run_scaling_tests.sh -q
# Or check system resources
docker stats
```

### Debug Mode

Enable verbose logging:
```bash
./scripts/run_scaling_tests.sh -v
```

### Manual Test Execution

Run individual test scenarios:
```bash
# Small scale only
./scripts/deploy_scale.sh -s small -c -v

# Check results manually
docker ps
docker stats
curl http://localhost:8001/docs
```

## Advanced Usage

### Custom Test Scenarios

Modify `test_scaling_validation.py` to add custom scenarios:

```python
test_scenarios = [
    ("custom", 25),    # Add custom scenario
    ("custom", 75),    # Another custom scenario
    # ... existing scenarios
]
```

### Performance Profiling

Enable detailed profiling:
```bash
# Enable Docker stats collection
docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" > stats.log &
TEST_PID=$!

# Run tests
./scripts/run_scaling_tests.sh

# Stop stats collection
kill $TEST_PID
```

### Integration with CI/CD

Example GitHub Actions workflow:

```yaml
name: Scaling Tests
on: [push, pull_request]
jobs:
  scaling:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - name: Run Scaling Tests
      run: ./scripts/run_scaling_tests.sh -q
    - name: Upload Results
      uses: actions/upload-artifact@v2
      with:
        name: scaling-results
        path: test_results/
```

## Contributing

### Adding New Tests

1. Add test function to `test_scaling_validation.py`
2. Update target metrics in `ScalingValidator`
3. Add documentation to this README
4. Update report template in `docs/scaling_test_report.md`

### Performance Improvements

1. Profile existing tests for bottlenecks
2. Optimize Docker resource usage
3. Improve parallel test execution
4. Enhance metric collection accuracy

## Support

For issues with the scaling test suite:

1. Check this README first
2. Review test logs in `test_results/`
3. Examine generated reports
4. Check system resources (Docker, disk space, memory)
5. Open an issue with detailed logs and system information

## Version History

- **v1.0** (November 2024): Initial implementation
  - Full scaling validation suite
  - Automated test execution
  - Performance graph generation
  - Comprehensive reporting

---

**Last Updated:** November 4, 2024  
**Test Suite Version:** 1.0  
**Compatibility:** CQKD DHT v1.0+