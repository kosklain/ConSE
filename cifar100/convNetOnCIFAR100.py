import cPickle
import time
import theano
import numpy as np
import theano.tensor as T

import climin.stops
import climin.initialize
from gensim.models.word2vec import Word2Vec

from breze.learn.cnn import Cnn
from breze.learn.data import one_hot

theano.config.exception_verbosity = 'high'

def get_data():
    train_file = 'pylearn2_gcn_whitened/train.pkl'
    test_file = 'pylearn2_gcn_whitened/test.pkl'
    f = open(train_file,'rb')
    train_set = cPickle.load(f)
    f = open(test_file)
    test_set = cPickle.load(f)
    X, Z = train_set.get_data()
    VX, VZ = test_set.get_data()
    Z = one_hot(Z, 10)
    VZ = one_hot(VZ, 10)
    X = X[:128*390]
    Z = Z[:128*390]
    VX = VX[:128*78]
    VZ = VZ[:128*78]
    X = np.array(X, dtype=np.float32)
    Z = np.array(Z, dtype=np.float32)
    VZ = np.array(VZ, dtype=np.float32)
    VX = np.array(VX, dtype=np.float32)
    return X, Z, VX, VZ

def convolutional_nets_on_CIFAR100(data):
    X, Z, VX, VZ = data
    max_passes = 100
    batch_size = 128
    max_iter = max_passes * X.shape[0] / batch_size
    n_report = X.shape[0] / (5*batch_size)
    stop = climin.stops.any_([
        climin.stops.after_n_iterations(max_iter),
        ])

    pause = climin.stops.modulo_n_iterations(n_report)
    optimizer = 'gd', {'steprate': 0.01, 'momentum': 0.9}
    m = Cnn(3072, [32, 64, 128], [50], 10,
            ['rectifier', 'rectifier', 'rectifier'], ['rectifier'],
            out_transfer='softmax', loss='nce', image_height=32, image_width=32,
            n_image_channel=3, optimizer=optimizer, batch_size=batch_size,
            max_iter=max_iter, pool_shapes=[[3, 3], [3, 3], [3, 3]],
            filter_shapes=[[5, 5], [5, 5], [5, 5]],
            pool_strides=[[2, 2], [2, 2], [2, 2]], padding=[2,2,2],
            lrnorm=[True, True, False],
            init_weights_stdev=[0.01, 0.1, 0.1, 0.1, 0.1])

    weight_decay = 0.04*((m.parameters.in_to_hidden**2).sum()) + \
                   0.04*((m.parameters.hidden_conv_to_hidden_conv_0**2).sum()) \
                   + 0.04*((m.parameters.hidden_conv_to_hidden_conv_1**2).sum())\
                   + 2*(m.parameters.hidden_conv_to_hidden_full**2).sum()
    weight_decay /= m.exprs['inpt'].shape[0]
    m.exprs['true_loss'] = m.exprs['loss']
    m.exprs['loss'] += weight_decay

    n_wrong = 1 - T.eq(T.argmax(m.exprs['output'], axis=1),
                       T.argmax(m.exprs['target'], axis=1)).mean()
    f_n_wrong = m.function(['inpt', 'target'], n_wrong)

    v_losses = []
    print 'max iter', max_iter

    start = time.time()
    keys = '#', 'val loss', 'seconds', 'train emp', 'val emp'
    header = '\t'.join(i for i in keys)
    print header
    print '-' * len(header)
    info = None
    for i, info in enumerate(m.powerfit((X, Z), (VX, VZ), stop, pause,
                                        eval_train_loss=False)):
        if info['n_iter'] % n_report != 0:
            continue
        passed = time.time() - start
        v_losses.append(info['val_loss'])
        f_wrong_val = m.apply_minibatches_function(f_n_wrong, VX, VZ)
        f_wrong_val = f_wrong_val*VX.shape[0]
        f_wrong_train = m.apply_minibatches_function(f_n_wrong, X[:len(VX)],
                                                     Z[:len(VZ)])*len(VX)
        info.update({
            'time': passed,
            'val_emp': f_wrong_val,
            'train_emp': f_wrong_train
        })
        row = '%(n_iter)i\t%(val_loss)g\t%(time)g\t%(train_emp)g\t%(val_emp)g' % info
        print row
    return info['best_pars']

if __name__ == "__main__":
    data = get_data()
    convolutional_nets_on_CIFAR100(data)
