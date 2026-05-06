

python  mono/tools/train.py \
        mono/configs/RAFTDecoder/vit.raft5.large.kitti.py \
        --use-tensorboard \
        --launcher None \
        --load-from weight/metric_depth_vit_large_800k.pth \
        --experiment_name set1 \
