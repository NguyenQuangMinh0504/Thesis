python3 main.py \
    -model lwf \
    --dataset kdd99 \
    -ms 2000 \
    -init 2 \
    -incre 2 \
    -net kdd_dnn \
    -p benchmark \
    --init_epoch 300 \
    --epochs 300 \
    --batch_size 128 \
    -d -1