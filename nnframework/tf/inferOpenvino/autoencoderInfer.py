# Copyright (c) 2020 Intel Corporation.

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import sys
import os
import cv2
import numpy as np
import logging as log
from time import time
from openvino.inference_engine import IENetwork, IECore
import base64
from PIL import Image
import io
import time
from scipy import spatial
import tensorflow as tf

TMP_FILE = "/tmp/tmp.png"

def convertBase64(imgb64):
    encimgb64 = imgb64.split(",")[1]
    pads = len(encimgb64) % 4
    if pads == 2:
        encimgb64 += "=="
    elif pads == 3:
        encimgb64 += "="

    imgb64 = base64.b64decode(encimgb64)
    img = Image.open(io.BytesIO(imgb64))
    img.save(TMP_FILE)


def generateLabels(labels):
    label = []
    for x in labels:
        lbl = x['name'].split('_')[1]
        label.append(lbl)
    return label


def autoencoderInfer(data):
    PATH = os.path.join(
        './data/{}_{}/model').format(data['jobId'], data['jobName'])
    DEVICE = 'CPU'

    # --------------------------- 1. Read IR Generated by ModelOptimizer (.xml and .bin files) ------------
    modelPath = os.path.join(PATH, 'FP32')
    model_xml = os.path.join(modelPath, 'frozen_inference_graph.xml')
    model_bin = os.path.splitext(model_xml)[0] + ".bin"

    log.info("Creating Inference Engine")
    ie = IECore()
    log.info("Loading network files:\n\t{}\n\t{}".format(model_xml, model_bin))
    net = IENetwork(model=model_xml, weights=model_bin)

    # --------------------------- 3. Read and preprocess input --------------------------------------------
    log.info("Preparing input blobs")
    input_blob = next(iter(net.inputs))
    out_blob = next(iter(net.outputs))
    n, c, h, w = net.inputs[input_blob].shape

    images = np.ndarray(shape=(n, c, h, w))
    convertBase64(data['image'])
    labels = generateLabels(data['labels'])
    for i in range(n):
        image = cv2.imread(TMP_FILE)
        if image.shape[:-1] != (h, w):
            image = cv2.resize(image, (w, h))
            image = image.transpose((2, 0, 1))
        images[i] = image
    log.info("Batch size is {}".format(n))
    log.info("Loading model to the plugin")
    exec_net = ie.load_network(network=net, device_name=DEVICE)
    inf_start = time.time()
    res = exec_net.infer(inputs={input_blob: images})
    res = res[out_blob]
    output = res[0]
    output = output*255
    output = output.transpose((1, 2, 0))
    image = image.transpose((1, 2, 0))
    tf_ssim = tf.image.ssim(tf.expand_dims(tf.convert_to_tensor(output, dtype='float32'),0), 
                            tf.expand_dims(tf.convert_to_tensor(image, dtype='float32'),0), 
                            1, filter_size=11, filter_sigma=1.5, k1=0.01, k2=0.03)
    score = tf.Session().run(tf_ssim)[0]
    log.info("Similarity score is {}".format(score))
    original = cv2.resize(image, (0, 0), fx=4, fy=4)
    outputImg = cv2.resize(output, (0, 0), fx=4, fy=4)
    score = ('similarity score: {:.4f}'.format(score))
    display = np.hstack((original, outputImg))
    
    cv2.putText(display, score, (50, 75),
                cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 2)
    retval, encoded = cv2.imencode('.jpeg', display)
    jpgb64 = base64.b64encode(encoded).decode('ascii')
    return jpgb64
