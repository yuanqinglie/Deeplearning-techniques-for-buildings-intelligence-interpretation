
def _make_divisible(v, divisor, min_value=None):
    if min_value is None:
        min_value = divisor
    new_v = max(min_value, int(v + divisor / 2) // divisor * divisor)
    if new_v < 0.9 * v:
        new_v += divisor
    return new_v

def relu6(x):
    return relu(x, max_value=6)

def _inverted_res_block(inputs, expansion, stride, alpha, filters, block_id, skip_connection, rate=1):
    in_channels = inputs.shape[-1].value  # inputs._keras_shape[-1]
    pointwise_conv_filters = int(filters * alpha)
    pointwise_filters = _make_divisible(pointwise_conv_filters, 8)
    x = inputs
    prefix = 'expanded_conv_{}_'.format(block_id)
    if block_id:
        # Expand
        x = Conv2D(expansion * in_channels, kernel_size=1, padding='same',
                   use_bias=False, activation=None,
                   name=prefix + 'expand')(x)
        x = BatchNormalization(epsilon=1e-3, momentum=0.999,
                               name=prefix + 'expand_BN')(x)
        x = Activation(relu6, name=prefix + 'expand_relu')(x)
    else:
        prefix = 'expanded_conv_'
    # Depthwise
    x = DepthwiseConv2D(kernel_size=3, strides=stride, activation=None,
                        use_bias=False, padding='same', dilation_rate=(rate, rate),
                        name=prefix + 'depthwise')(x)
    x = BatchNormalization(epsilon=1e-3, momentum=0.999,
                           name=prefix + 'depthwise_BN')(x)

    x = Activation(relu6, name=prefix + 'depthwise_relu')(x)

    # Project
    x = Conv2D(pointwise_filters,
               kernel_size=1, padding='same', use_bias=False, activation=None,
               name=prefix + 'project')(x)
    x = BatchNormalization(epsilon=1e-3, momentum=0.999,
                           name=prefix + 'project_BN')(x)

    if skip_connection:
        return Add(name=prefix + 'add')([inputs, x])

    # if in_channels == pointwise_filters and stride == 1:
    #    return Add(name='res_connect_' + str(block_id))([inputs, x])

    return x

def get_mobilenet_encoder(inputs_size, downsample_factor=8):
    if downsample_factor == 16:
        block4_dilation = 1
        block5_dilation = 2
        block4_stride = 2
    elif downsample_factor == 8:
        block4_dilation = 2
        block5_dilation = 4
        block4_stride = 1
    else:
        raise ValueError('Unsupported factor - `{}`, Use 8 or 16.'.format(downsample_factor))
    
    # 473,473,3
    inputs = Input(shape=inputs_size)

    alpha=1.0
    first_block_filters = _make_divisible(32 * alpha, 8)
    # 473,473,3 -> 237,237,32
    x = Conv2D(first_block_filters,
                kernel_size=3,
                strides=(2, 2), padding='same',
                use_bias=False, name='Conv')(inputs)
    x = BatchNormalization(
        epsilon=1e-3, momentum=0.999, name='Conv_BN')(x)
    x = Activation(relu6, name='Conv_Relu6')(x)

    # 237,237,32 -> 237,237,16
    x = _inverted_res_block(x, filters=16, alpha=alpha, stride=1,
                            expansion=1, block_id=0, skip_connection=False)

    #---------------------------------------------------------------#
    # 237,237,16 -> 119,119,24
    x = _inverted_res_block(x, filters=24, alpha=alpha, stride=2,
                            expansion=6, block_id=1, skip_connection=False)
    x = _inverted_res_block(x, filters=24, alpha=alpha, stride=1,
                            expansion=6, block_id=2, skip_connection=True)
                            
    #---------------------------------------------------------------#
    # 119,119,24 -> 60,60.32
    x = _inverted_res_block(x, filters=32, alpha=alpha, stride=2,
                            expansion=6, block_id=3, skip_connection=False)
    x = _inverted_res_block(x, filters=32, alpha=alpha, stride=1,
                            expansion=6, block_id=4, skip_connection=True)
    x = _inverted_res_block(x, filters=32, alpha=alpha, stride=1,
                            expansion=6, block_id=5, skip_connection=True)
    f1 = x
    #---------------------------------------------------------------#
    # 60,60,32 -> 30,30.64
    x = _inverted_res_block(x, filters=64, alpha=alpha, stride=block4_stride,
                            expansion=6, block_id=6, skip_connection=False)
    x = _inverted_res_block(x, filters=64, alpha=alpha, stride=1, rate=block4_dilation,
                            expansion=6, block_id=7, skip_connection=True)
    x = _inverted_res_block(x, filters=64, alpha=alpha, stride=1, rate=block4_dilation,
                            expansion=6, block_id=8, skip_connection=True)
    x = _inverted_res_block(x, filters=64, alpha=alpha, stride=1, rate=block4_dilation,
                           expansion=6, block_id=9, skip_connection=True)
    f2 = x
    # 30,30.64 -> 30,30.96
    x = _inverted_res_block(x, filters=96, alpha=alpha, stride=1, rate=block4_dilation,
                            expansion=6, block_id=10, skip_connection=False)
    x = _inverted_res_block(x, filters=96, alpha=alpha, stride=1, rate=block4_dilation,
                            expansion=6, block_id=11, skip_connection=True)
    x = _inverted_res_block(x, filters=96, alpha=alpha, stride=1, rate=block4_dilation,
                            expansion=6, block_id=12, skip_connection=True)
    # branch network
    f4 = x

    #---------------------------------------------------------------#
    # 30,30.96 -> 30,30,160 -> 30,30,320
    x = _inverted_res_block(x, filters=160, alpha=alpha, stride=1, rate=block4_dilation,  # 1!
                            expansion=6, block_id=13, skip_connection=False)
    x = _inverted_res_block(x, filters=160, alpha=alpha, stride=1, rate=block5_dilation,
                            expansion=6, block_id=14, skip_connection=True)
    x = _inverted_res_block(x, filters=160, alpha=alpha, stride=1, rate=block5_dilation,
                            expansion=6, block_id=15, skip_connection=True)

    x = _inverted_res_block(x, filters=320, alpha=alpha, stride=1, rate=block5_dilation,
                            expansion=6, block_id=16, skip_connection=False)
    f5 = x
    return [inputs,f2,f3,f4,f5]



from keras.layers import Activation, Conv2D
import keras.backend as K
import tensorflow as tf
from keras.layers import Layer
from keras.activations import softmax
import numpy as np
from keras.layers.pooling import  GlobalAveragePooling2D as GAP
from keras.layers import  add
from keras.layers import concatenate,BatchNormalization
from keras.layers import Lambda

def Codecontext(input,n=4,filters2=2):
        
        input_shape1 = input.get_shape().as_list()
        batch, h, w, filters = input_shape1
        filters1=int(filters // n)
        

        b = Conv2D(filters1, 1, use_bias=False, kernel_initializer='he_normal')(input)
        c1 = Conv2D(filters2, 1, use_bias=False, kernel_initializer='he_normal')(input)
        
        vec_bT = Lambda(lambda xx: tf.transpose(K.reshape(xx, (-1, h * w, filters1)),(0, 2, 1)))(b)

        softmax_vec_b =Lambda(lambda xx: softmax(vec_bT,axis=1))(vec_bT ) 
        c =Lambda(lambda xx:K.reshape(c1, (-1, h * w, filters2)))(c1)
           
        bTc=Lambda(lambda xx:K.batch_dot(xx[0],xx[1]))([softmax_vec_b, c])
        return [bTc,c1]

def Decocontext(inputs,n=4,C=2):
        input=inputs[0]
        # n: number of codeword
        
        input1=inputs[1]
        input_shape = input.get_shape().as_list()
        filters2_1 = input1.get_shape().as_list()[3]
        _, h, w, filters = input_shape
        filters1=int(filters // n)
        filters2=int(filters2_1 // C)
        filters3=int(filters2_1 // n)
        print("Number of codeword:",filters3)
        print("Number of channels reduction:",filters2)
        
        #codebook,c1 = self.Codebook(input1)
        codecontext,c1 = Codecontext(input1,n,filters2)
       

        a = Conv2D(filters2, 1, use_bias=False, kernel_initializer='he_normal')(input)
      
        gap=GAP()(c1)
        
        a_gap=add([a,gap])
        

        a_gap=Conv2D(filters3, 1, use_bias=False, kernel_initializer='he_normal')(a_gap)
        
        a_gap_vec=Lambda(lambda xx:K.reshape(xx,(-1, h * w, filters3) )) ( a_gap)
        
        acodebook= Lambda(lambda xx:K.reshape(K.batch_dot(xx[0],xx[1]), (-1, h,w, filters2) )) ([a_gap_vec,codecontext])
        
        acodebook_con= concatenate([acodebook,a], axis=3, name='acodebook_con' )
        acodebook_con=Conv2D(filters2, 1, use_bias=False, kernel_initializer='he_normal')(acodebook_con)
        acodebook_con= BatchNormalization(axis=3)(acodebook_con)
        acodebook_con = Activation('relu', name='acodebook_Act')(acodebook_con)
        out= acodebook_con


        return out

# Test Decocontext
"""
from keras.preprocessing import image
#from keras.applications.vgg16 import preprocess_input, decode_predictions
import cv2
from google.colab.patches import cv2_imshow
import numpy as np
import matplotlib.pyplot as plt


img_path = '/train/image/100.tif'
img = image.load_img(img_path, target_size=(512, 512))

x = image.img_to_array(img)/255
x = tf.cast(np.expand_dims(x, axis=0),dtype=tf.float32)
x1 = Conv2D(64, kernel_size=(3,3),strides=1,padding='same', use_bias=True, kernel_initializer='he_normal')(x)
x2 = Conv2D(64, kernel_size=(3,3),strides=1,padding='same', use_bias=True, kernel_initializer='he_normal')(x1)
y=  Decocontext([x2,x1],n=4,C=2)
y1 = Conv2D(3, kernel_size=(3,3),strides=1,padding='same', use_bias=False, kernel_initializer='he_normal')(y)
y1=K.eval(y1)
y2=K.eval(x2)
print(y1.shape)

plt.imshow(img)
plt.show( )
cv2_imshow(y1[0])
"""

from keras.models import Model
from keras.layers import Input, Activation, Conv2D, Dropout
from keras.layers import MaxPooling2D, BatchNormalization
from keras.layers import UpSampling2D
from keras.layers import concatenate
from keras.layers import add
#from layers.attention import PAM, CAM
import numpy as np
from keras.layers import Softmax,Reshape
from keras.layers import Lambda

def conv3x3(x, out_filters, strides=(1, 1)):
    x = Conv2D(out_filters, 3, padding='same', strides=strides, use_bias=False, kernel_initializer='he_normal')(x)
    return x


def Conv2d_BN(x, nb_filter, kernel_size, strides=(1, 1), padding='same', use_activation=True):
    x = Conv2D(nb_filter, kernel_size, padding=padding, strides=strides, kernel_initializer='he_normal')(x)
    x = BatchNormalization(axis=3)(x)
    if use_activation:
        x = Activation('relu')(x)
        return x
    else:
        return x


def basic_Block(input, out_filters, strides=(1, 1), with_conv_shortcut=False):
    x = conv3x3(input, out_filters, strides)
    x = BatchNormalization(axis=3)(x)
    x = Activation('relu')(x)

    x = conv3x3(x, out_filters)
    x = BatchNormalization(axis=3)(x)

    if with_conv_shortcut:
        residual = Conv2D(out_filters, 1, strides=strides, use_bias=False, kernel_initializer='he_normal')(input)
        residual = BatchNormalization(axis=3)(residual)
        x = add([x, residual])
    else:
        x = add([x, input])

    x = Activation('relu')(x)
    return x


def bottleneck_Block(input, out_filters, strides=(1, 1), dilation=(1, 1), with_conv_shortcut=False):
    expansion = 4
    de_filters = int(out_filters / expansion)

    x = Conv2D(de_filters, 1, use_bias=False, kernel_initializer='he_normal')(input)
    x = BatchNormalization(axis=3)(x)
    x = Activation('relu')(x)

    x = Conv2D(de_filters, 3, strides=strides, padding='same',
               dilation_rate=dilation, use_bias=False, kernel_initializer='he_normal')(x)
    x = BatchNormalization(axis=3)(x)
    x = Activation('relu')(x)

    x = Conv2D(out_filters, 1, use_bias=False, kernel_initializer='he_normal')(x)
    x = BatchNormalization(axis=3)(x)

    if with_conv_shortcut:
        residual = Conv2D(out_filters, 1, strides=strides, use_bias=False, kernel_initializer='he_normal')(input)
        residual = BatchNormalization(axis=3)(residual)
        x = add([x, residual])
    else:
        x = add([x, input])

    x = Activation('relu')(x)
    return x

def Branch_Block(input,filters,out_filters, strides=(1, 1), dilation=(1, 1), with_conv_shortcut=False):


    x = Conv2D(filters, 3, strides=strides, padding='same',
               dilation_rate=dilation, use_bias=False, kernel_initializer='he_normal')(x)
    x = BatchNormalization(axis=3)(x)
    x = Activation('relu')(x)

    x = Conv2D(filters, 3, strides=strides, padding='same',
               dilation_rate=dilation, use_bias=False, kernel_initializer='he_normal')(x)
    x = BatchNormalization(axis=3)(x)
    x = Activation('relu')(x)


    x = Conv2D(out_filters, 1, use_bias=False, kernel_initializer='he_normal')(x)
    x = BatchNormalization(axis=3)(x)

    if with_conv_shortcut:
        residual = Conv2D(out_filters, 1, strides=strides, use_bias=False, kernel_initializer='he_normal')(input)
        residual = BatchNormalization(axis=3)(residual)
        x = add([x, residual])
    else:
        x = add([x, input])

    x = Activation('relu')(x)
    x = MaxPooling2D( pool_size=(3, 3),strides=2,padding='same',data_format='channels_last')(x)

    return x

def code_resnet101(height, width, channel, classes,n,C):
    input = Input(shape=(height, width, channel))
   
    conv1_1 = Conv2D(64, 7, strides=(2, 2), padding='same', use_bias=False, kernel_initializer='he_normal')(input)
    
    conv1_1 = BatchNormalization(axis=3)(conv1_1)
    conv1_1 = Activation('relu')(conv1_1)
    conv1_2 = MaxPooling2D(pool_size=(3, 3), strides=(2, 2), padding='same')(conv1_1)

    # conv2_x  1/4
    conv2_1 = bottleneck_Block(conv1_2, 256, strides=(1, 1), with_conv_shortcut=True)
    conv2_2 = bottleneck_Block(conv2_1, 256)
    conv2_3 = bottleneck_Block(conv2_2, 256)

    # conv3_x  1/8
    conv3_1 = bottleneck_Block(conv2_3, 512, strides=(2, 2), with_conv_shortcut=True)
    conv3_2 = bottleneck_Block(conv3_1, 512)
    conv3_3 = bottleneck_Block(conv3_2, 512)
    conv3_4 = bottleneck_Block(conv3_3, 512)

    # conv4_x  1/16
    conv4_1 = bottleneck_Block(conv3_4, 1024, strides=(2, 2), dilation=(1, 1), with_conv_shortcut=True)
    conv4_2 = bottleneck_Block(conv4_1, 1024)
    conv4_3 = bottleneck_Block(conv4_2, 1024)
    conv4_4 = bottleneck_Block(conv4_3, 1024)
    conv4_5 = bottleneck_Block(conv4_4, 1024)
    conv4_6 = bottleneck_Block(conv4_5, 1024)
    conv4_7 = bottleneck_Block(conv4_6, 1024)
    conv4_8 = bottleneck_Block(conv4_7, 1024)
    conv4_9 = bottleneck_Block(conv4_8, 1024)
    conv4_10 = bottleneck_Block(conv4_9, 1024)
    conv4_11 = bottleneck_Block(conv4_10, 1024)
    conv4_12 = bottleneck_Block(conv4_11, 1024)
    conv4_13 = bottleneck_Block(conv4_12, 1024)
    conv4_14 = bottleneck_Block(conv4_13, 1024)
    conv4_15 = bottleneck_Block(conv4_14, 1024)
    conv4_16 = bottleneck_Block(conv4_15, 1024)
    conv4_17 = bottleneck_Block(conv4_16, 1024)
    conv4_18 = bottleneck_Block(conv4_17, 1024)
    conv4_19 = bottleneck_Block(conv4_18, 1024)
    conv4_20 = bottleneck_Block(conv4_19, 1024)
    conv4_21 = bottleneck_Block(conv4_20, 1024)
    conv4_22 = bottleneck_Block(conv4_21, 1024)
    conv4_23 = bottleneck_Block(conv4_22, 1024)

    # conv5_x  1/32
    conv5_1 = bottleneck_Block(conv4_23, 2048, strides=(2, 2), dilation=(1, 1), with_conv_shortcut=True)
    conv5_2 = bottleneck_Block(conv5_1, 2048)
    conv5_3 = bottleneck_Block(conv5_2, 2048)
   

    # ------------------------Pyramid feature Fusion-----------------------------------------
    # Fusion  1/32
    conv6_1 = Conv2D(512, 1, use_bias=False, kernel_initializer='he_normal')(conv5_3)
    conv6_2_1 = Conv2D(512, 1, use_bias=False, kernel_initializer='he_normal')(conv4_23)

    size_before1 = tf.keras.backend.int_shape(conv6_1)
    
    conv6_2 = Lambda(lambda xx:tf.image.resize_images(xx,size_before1[1:3]))(conv6_2_1)
    conv6_3 = Lambda(lambda xx:tf.image.resize_images(xx,size_before1[1:3]))(conv3_4)
    conv6_4 = Lambda(lambda xx:tf.image.resize_images(xx,size_before1[1:3]))(conv2_3)

    merge1 = concatenate([conv6_1, conv6_2, conv6_3,conv6_4], axis=3)
   
    # Fusion  1/8
    #size_before2 = tf.keras.backend.int_shape(conv3_4)
    #conv7_1 = Lambda(lambda xx:tf.image.resize_images(xx,size_before2[1:3]))(conv6_1)
    #conv7_2 = Lambda(lambda xx:tf.image.resize_images(xx,size_before2[1:3]))(conv6_2_1)
    #merge2 = concatenate([conv7_1, conv7_2, conv3_4], axis=3)

    # Fusion 1/4
    size_before3 = tf.keras.backend.int_shape(conv2_3)
    conv7_1 = Lambda(lambda xx:tf.image.resize_images(xx,size_before3[1:3]))(conv6_1)
    conv7_2 = Lambda(lambda xx:tf.image.resize_images(xx,size_before3[1:3]))(conv6_2_1)
    conv7_3 = Lambda(lambda xx:tf.image.resize_images(xx,size_before3[1:3]))(conv3_4)
    merge2 = concatenate([conv7_1, conv7_2, conv7_3,conv2_3], axis=3)
    print(merge2)
    # ------------------------Pyramid feature Fusion-----------------------------------------
    
    # Decoder
    codeword =  Codeword([merge2,merge1],n,C) # n:number of codeword;C:channels redutction

    # Last Conv Layer and Prediction

    conv8_1 = Conv2D(384, kernel_size=3, padding='same', strides=(1, 1), kernel_initializer='he_normal',name='fine_tune1')(codeword)
    conv8_1 = BatchNormalization(axis=3)(conv8_1)
    conv8_1 = Activation('relu')(conv8_1) #conv8_1 = Conv2d_BN(codeword, 384, 3, strides=(1, 1), padding='same', use_activation=True)
   
    conv8_1 = Dropout(0.5)(conv8_1)
    size_before4 = tf.keras.backend.int_shape(input)
    conv8_2 = Lambda(lambda xx:tf.image.resize_images(xx,size_before4[1:3]))(conv8_1)
    conv8_3 = Conv2D(classes, 1, kernel_initializer='he_normal',name='fine_tune2')(conv8_2)
    conv8_3 = BatchNormalization(name='fine_tune3',axis=3)(conv8_3)#conv8_3 = Conv2d_BN(conv8_2, classes, 1, use_activation=None)

    y    = Reshape((-1,classes))(conv8_3)
    activation = Softmax( )(y)
    # activation = Activation('sigmoid', name='Classification')(conv11)
    model = Model(inputs=input, outputs=activation)
    return model

#-------------------------------------------------------------#
#   M_ResNet50
#-------------------------------------------------------------#
from __future__ import print_function

import numpy as np
from keras import layers

from keras.layers import Input
from keras.layers import Dense,Conv2D,MaxPooling2D,ZeroPadding2D,AveragePooling2D
from keras.layers import Activation,BatchNormalization,Flatten
from keras.models import Model

from keras.preprocessing import image
import keras.backend as K
from keras.utils.data_utils import get_file
from keras.applications.imagenet_utils import decode_predictions
from keras.applications.imagenet_utils import preprocess_input


def identity_block(input_tensor, kernel_size, filters, stage, block, dilation_rate=1):

    filters1, filters2, filters3 = filters

    conv_name_base = 'res' + str(stage) + block + '_branch'
    bn_name_base = 'bn' + str(stage) + block + '_branch'

    x = Conv2D(filters1, (1, 1), name=conv_name_base + '2a', use_bias=False)(input_tensor)
    x = BatchNormalization(name=bn_name_base + '2a')(x)
    x = Activation('relu')(x)

    x = Conv2D(filters2, kernel_size, padding='same', dilation_rate = dilation_rate, name=conv_name_base + '2b', use_bias=False)(x)
    x = BatchNormalization(name=bn_name_base + '2b')(x)
    x = Activation('relu')(x)

    x = Conv2D(filters3, (1, 1), name=conv_name_base + '2c', use_bias=False)(x)
    x = BatchNormalization(name=bn_name_base + '2c')(x)

    x = layers.add([x, input_tensor])
    x = Activation('relu')(x)
    return x


def conv_block(input_tensor, kernel_size, filters, stage, block, strides=(2, 2), dilation_rate=1):

    filters1, filters2, filters3 = filters

    conv_name_base = 'res' + str(stage) + block + '_branch'
    bn_name_base = 'bn' + str(stage) + block + '_branch'

    x = Conv2D(filters1, (1, 1), strides=strides,
               name=conv_name_base + '2a', use_bias=False)(input_tensor)
    x = BatchNormalization(name=bn_name_base + '2a')(x)
    x = Activation('relu')(x)

    x = Conv2D(filters2, kernel_size, padding='same', dilation_rate = dilation_rate,
               name=conv_name_base + '2b', use_bias=False)(x)
    x = BatchNormalization(name=bn_name_base + '2b')(x)
    x = Activation('relu')(x)

    x = Conv2D(filters3, (1, 1), name=conv_name_base + '2c', use_bias=False)(x)
    x = BatchNormalization(name=bn_name_base + '2c')(x)

    shortcut = Conv2D(filters3, (1, 1), strides=strides,
                      name=conv_name_base + '1', use_bias=False)(input_tensor)
    shortcut = BatchNormalization(name=bn_name_base + '1')(shortcut)

    x = layers.add([x, shortcut])
    x = Activation('relu')(x)
    return x
    
def get_resnet50_encoder(inputs_size, downsample_factor=8):
    if downsample_factor == 16:
        block4_dilation = 1
        block5_dilation = 2
        block4_stride = 2
    elif downsample_factor == 8:
        block4_dilation = 2
        block5_dilation = 4
        block4_stride = 1
    else:
        raise ValueError('Unsupported factor - `{}`, Use 8 or 16.'.format(downsample_factor))
    img_input = Input(shape=inputs_size)

    x = ZeroPadding2D(padding=(1, 1), name='conv1_pad')(img_input)
    x = Conv2D(filters=64, kernel_size=(3, 3), strides=(2, 2), name='conv1', use_bias=False)(x)
    x = BatchNormalization(axis=-1, name='bn_conv1')(x)
    x = Activation('relu')(x)

    x = ZeroPadding2D(padding=(1, 1), name='conv2_pad')(x)
    x = Conv2D(filters=64, kernel_size=(3, 3), strides=(1, 1), name='conv2', use_bias=False)(x)
    x = BatchNormalization(axis=-1, name='bn_conv2')(x)
    x = Activation(activation='relu')(x)

    x = ZeroPadding2D(padding=(1, 1), name='conv3_pad')(x)
    x = Conv2D(filters=128, kernel_size=(3, 3), strides=(1, 1), name='conv3', use_bias=False)(x)
    x = BatchNormalization(axis=-1, name='bn_conv3')(x)
    x = Activation(activation='relu')(x)

    x = ZeroPadding2D(padding=(1, 1), name='pool1_pad')(x)
    x = MaxPooling2D((3, 3), strides=(2, 2))(x)
    f1 = x

    x = conv_block(x, 3, [64, 64, 256], stage=2, block='a', strides=(1, 1))
    x = identity_block(x, 3, [64, 64, 256], stage=2, block='b')
    x = identity_block(x, 3, [64, 64, 256], stage=2, block='c')
    f2 = x
    
    x = conv_block(x, 3, [128, 128, 512], stage=3, block='a')
    x = identity_block(x, 3, [128, 128, 512], stage=3, block='b')
    x = identity_block(x, 3, [128, 128, 512], stage=3, block='c')
    x = identity_block(x, 3, [128, 128, 512], stage=3, block='d')
    f3 = x

    x = conv_block(x, 3, [256, 256, 1024], stage=4, block='a', strides=(block4_stride,block4_stride))
    x = identity_block(x, 3, [256, 256, 1024], stage=4, block='b', dilation_rate=block4_dilation)
    x = identity_block(x, 3, [256, 256, 1024], stage=4, block='c', dilation_rate=block4_dilation)
    x = identity_block(x, 3, [256, 256, 1024], stage=4, block='d', dilation_rate=block4_dilation)
    x = identity_block(x, 3, [256, 256, 1024], stage=4, block='e', dilation_rate=block4_dilation)
    x = identity_block(x, 3, [256, 256, 1024], stage=4, block='f', dilation_rate=block4_dilation)
    f4 = x

    x = conv_block(x, 3, [512, 512, 2048], stage=5, block='a', strides=(1,1), dilation_rate=block4_dilation)
    x = identity_block(x, 3, [512, 512, 2048], stage=5, block='b', dilation_rate=block5_dilation)
    x = identity_block(x, 3, [512, 512, 2048], stage=5, block='c', dilation_rate=block5_dilation)
    f5 = x 

    return [inputs,f2,f3,f4,f5]

def pool_block(feats, pool_factor, out_channel,flag=1):
  h = K.int_shape(feats)[1]
  w = K.int_shape(feats)[2]
  # e.g strides = [30,30],[15,15],[10,10],[5,5]
	# e.g. poolsize 30/6=5 30/3=10 30/2=15 30/1=30
  pool_size = [int(np.round(float(h)/pool_factor)),int(np.round(float(w)/pool_factor))]
  # average pooling with different ratio
  if flag== 1:
    x = AveragePooling2D(pool_size , data_format='channels_last' , strides=pool_size, padding='same')(feats)
    
  else:
    x = MaxPooling2D(pool_size , data_format='channels_last' , strides=strides, padding='same')(feats)
  return x

def Pyramid_context(pool_factor,out_channel,backbone='resnet50',aux_branch=True,flag=1,n=4,filters2=2):
   if backbone=="resnet101":
     featue= get_resnet101_encoder(inputs_size,downsample_factor=downsample_factor)
     img_input= feaure[0]
     f4= feaure[3]
     f5= feaure[4]
     out_channel = 2048
   elif backbone=="molilenet":
     feature= get_mobilenet_encoder(inputs_size,downsample_factor=downsample_factor)
     img_input= feaure[0]
     f4= feaure[3]
     f5= feaure[4]
     out_channel = 320
   elif backbone== "resnet50":
     feature= get_resnet50_encoder(inputs_size,downsample_factor=downsample_factor)
     img_input= feaure[0]
     f4= feaure[3]
     f5= feaure[4]
     out_channel = 2048
   input_shape1 = input.get_shape().as_list()
   batch, h, w, filters = input_shape1
   filters1=int(filters // n)
   pool_factors= [1,2,3,6] # [1,2,4,6], [1,3,6,8],[1,3,4,8]
   pool_outs = []    

   b = Conv2D(filters1, 1, use_bias=False, kernel_initializer='he_normal')(f5)
   c1 = Conv2D(filters2, 1, use_bias=False, kernel_initializer='he_normal')(f4)

   for p in pool_factors:
      pooling_b = pool_block(b, p, out_channel)
      pooling_c1 = pool_block(c1, p, out_channel)

      vec_bT = Lambda(lambda xx: tf.transpose(K.reshape(xx, (-1, h * w, filters1)),(0, 2, 1)))(pooling_b)

      softmax_vec_b =Lambda(lambda xx: softmax(vec_bT,axis=1))(vec_bT ) 
      c =Lambda(lambda xx:K.reshape(c1, (-1, h * w, filters2)))(pooling_c1)
           
      bTc=Lambda(lambda xx:K.batch_dot(xx[0],xx[1]))([softmax_vec_b, c])
      pool_outs.append(pooled)
   bTc = Concatenate(axis=0)(pool_outs)
   



   return [bTc,c1,feaure]



def SAM( input,filters1,k,filters2 ):

   f4= input[1]
   f5= input2[2]
   b = Conv2D(filters1, 1, use_bias=False, kernel_initializer='he_normal')(f5)
   c1 = Conv2D(filters2, 1, use_bias=False, kernel_initializer='he_normal')(f4)
   vec_bT = Lambda(lambda xx: tf.transpose(K.reshape(xx, (-1, h * w, filters1)),(0, 2, 1)))(b)
   vec_c = Lambda(lambda xx: K.reshape(xx, (-1, h * w, filters2)),(0, 2, 1))(c1)
   bTc=Lambda(lambda xx:K.batch_dot(xx[0],xx[1]))([vec_c,vec_bT])
   maxpool_spatial = Lambda(lambda x: K.max(x, axis=0, keepdims=True))(bTc)
   avgpool_spatial = Lambda(lambda x: K.mean(x, axis=0, keepdims=True))(bTc)
   max_avg_pool_spatial = Concatenate(axis=2)([maxpool_spatial, avgpool_spatial])
   atten= Lambda(lambda xx:K.reshape(xx, (-1, h,w, 2) ))(max_avg_pool_spatial)
   atten = Conv2D(1, kernel_size=k, use_bias=False, kernel_initializer='he_normal')(atten)
   atten =Lambda(lambda xx: softmax(vec_bT,axis=1))(atten )
   out=Lambda(lambda xx:K.batch_dot(xx[0],xx[1]))([c1, atten])

   return out

def Decocontext(inputs, pool_factor,out_channel,backbone='resnet50',aux_branch=True,flag=1,n=4,filters2=2,C=2):
        input=inputs[0]
        # n: the number of global contextual code
        
        input1=inputs[1]
        input_shape = input.get_shape().as_list()
        filters2_1 = input1.get_shape().as_list()[3]
        _, h, w, filters = input_shape
        filters1=int(filters // n)
        filters2=int(filters2_1 // C)
        filters3=int(filters2_1 // n)
        print("Number of contextual code:",filters3)
        print("Number of channels reduction:",filters2)
        
        #codebook,c1 = self.Codebook(input1)
        codecontext,c1,feaure = Pyramid_context( pool_factor,out_channel,backbone,aux_branch,flag,n=4,filters2=2)
       

        a = Conv2D(filters2, 1, use_bias=False, kernel_initializer='he_normal')(input)
      
        gap=GAP()(c1)
        
        a_gap=add([a,gap])      
        a_gap=Conv2D(filters3, 1, use_bias=False, kernel_initializer='he_normal')(a_gap)
        
        a_gap_vec=Lambda(lambda xx:K.reshape(xx,(-1, h * w, filters3) )) ( a_gap)
        
        acodebook= Lambda(lambda xx:K.reshape(K.batch_dot(xx[0],xx[1]), (-1, h,w, filters2) )) ([a_gap_vec,codecontext])
        """
        acodebook_con= concatenate([acodebook,a], axis=3, name='acodebook_con' )
        acodebook_con=Conv2D(filters2, 1, use_bias=False, kernel_initializer='he_normal')(acodebook_con)
        acodebook_con= BatchNormalization(axis=3)(acodebook_con)
        acodebook_con = Activation('relu', name='acodebook_Act')(acodebook_con)
        """
        acodebook_con= add([acodebook,a], name='acodebook_con' )
        out= acodebook_con

        return out
