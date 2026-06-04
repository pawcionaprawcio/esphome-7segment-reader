CXX      = g++
CXXFLAGS = -std=c++17 -I../../components -Wall -Wextra -MMD -MP

test: test_logic
	./test_logic

test_logic: test_logic.cpp
	$(CXX) $(CXXFLAGS) test_logic.cpp -o test_logic

clean:
	rm -f test_logic test_logic.d

-include test_logic.d
