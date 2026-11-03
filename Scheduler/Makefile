CXX := g++

BIN_DIR := bin

SERVER_SRC := controller.cc
SCHED_SRC  := scheduler.cc

SERVER_BIN := $(BIN_DIR)/server
SCHED_BIN  := $(BIN_DIR)/scheduler

BASE_FLAGS := -std=c++17
SYS_FLAGS  := -lrt -pthread -I /usr/include/eigen3 -I ../Common
EXTRA_FLAGS ?=

CXXFLAGS := $(BASE_FLAGS) $(SYS_FLAGS) $(EXTRA_FLAGS)

all: $(SERVER_BIN) $(SCHED_BIN)

$(BIN_DIR):
	mkdir -p $(BIN_DIR)

$(SERVER_BIN): $(SERVER_SRC) | $(BIN_DIR)
	$(CXX) $< \
	../Common/jetson/jetson_power_monitor.cpp \
	../Common/jetson/ina260_reader.cpp \
	../Common/jetson/jtop_reader.cpp \
	../Common/jetson/tegrastats_monitor.cpp \
	../Common/jetson/time_utils.cpp \
	-o $@ $(CXXFLAGS)

$(SCHED_BIN): $(SCHED_SRC) | $(BIN_DIR)
	$(CXX) $< -o $@ $(CXXFLAGS)

clean:
	rm -rf $(BIN_DIR)

print-flags:
	@echo $(CXXFLAGS)

.PHONY: all clean print-flags
