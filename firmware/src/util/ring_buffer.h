// ring_buffer.h - fixed-capacity POD ring buffer, no Arduino/FreeRTOS deps.
//
// Not thread-safe by itself; callers that share an instance across tasks
// must guard access with their own mutex/critical section (e.g. the
// digital_input edge-window buffers, or a future serial log buffer).
#pragma once

#include <cstddef>

template <typename T, size_t N>
class RingBuffer {
public:
    static_assert(N > 0, "RingBuffer capacity must be > 0");

    RingBuffer() = default;

    // Pushes a value. If the buffer is full, overwrites the oldest element
    // (classic overwrite-on-overflow ring buffer behavior).
    void push(const T& value) {
        buf_[head_] = value;
        head_ = (head_ + 1) % N;
        if (count_ < N) {
            ++count_;
        } else {
            tail_ = (tail_ + 1) % N; // oldest slot just got overwritten
        }
    }

    // Pops the oldest value into `out`. Returns false if empty.
    bool pop(T* out) {
        if (count_ == 0) {
            return false;
        }
        *out = buf_[tail_];
        tail_ = (tail_ + 1) % N;
        --count_;
        return true;
    }

    // Peeks at the oldest value without removing it. Returns false if empty.
    bool peek(T* out) const {
        if (count_ == 0) {
            return false;
        }
        *out = buf_[tail_];
        return true;
    }

    void clear() {
        head_ = 0;
        tail_ = 0;
        count_ = 0;
    }

    bool empty() const { return count_ == 0; }
    bool full() const { return count_ == N; }
    size_t size() const { return count_; }
    size_t capacity() const { return N; }

private:
    T buf_[N]{};
    size_t head_ = 0; // next write index
    size_t tail_ = 0; // next read index
    size_t count_ = 0;
};
