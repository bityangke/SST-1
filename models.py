import torch
import torch.nn as nn

class SST(nn.Module):
    """
    Container module with 1D convolutions to generate proposals
    """

    def __init__(self,
        video_dim=500,
        videohidden_dim=512,
        videovec_dim=512,
        hidden_dim=512,
        dropout=0,
        W=64,
        K=64,
        rnn_type='GRU',
        rnn_num_layers=2,
        rnn_dropout=0.2,
        rnn_batch_size=256,
    ):
        super(SST, self).__init__()
        self.rnn = getattr(nn, rnn_type)(videovec_dim, hidden_dim, rnn_num_layers, batch_first=True, dropout=rnn_dropout)
        self.scores = torch.nn.Linear(hidden_dim, K)

        # Saving arguments
        self.video_dim = video_dim
        self.videohidden_dim = videohidden_dim
        self.videovec_dim = videovec_dim
        self.W = W
        self.rnn_type = rnn_type
        self.rnn_num_layers = rnn_num_layers
        self.rnn_dropout = rnn_dropout
        self.K = K
        self.rnn_batch_size = rnn_batch_size

    def eval(self):
        self.rnn.dropout = 0

    def forward(self, features):
        features = features[0, :, :, :]
        N, T, _ = features.size()

        rnn_output, _ = self.rnn(features)
        rnn_output = rnn_output.contiguous()
        rnn_output = rnn_output.view(rnn_output.size(0)*rnn_output.size(1), rnn_output.size(2))
        outputs = torch.sigmoid(self.scores(rnn_output))
        return outputs.view(-1)

    def slow_compute_loss(self, outputs, masks, labels):
        """
        Used mainly for checking the actual loss function
        """
        labels = torch.autograd.Variable(labels[0, :, :, :])
        masks = torch.autograd.Variable(masks[0, :, :, :])
        outputs = outputs.view(-1, self.W, self.K)
        loss = 0.0
        print outputs.size()
        for n in range(outputs.size(0)):
            for t in range(self.W):
                w1 = torch.sum(outputs[n, t, :])/outputs.numel()
                w0 = 1.0 - w1
                for j in range(self.K):
                    loss -= w1 * labels[n, t, j] * torch.log(outputs[n,t,j])
                    loss -= w0 * (1.0 - labels[n, t, j]) * torch.log(1.0 - outputs[n,t,j])
            print n, loss
        return loss

    def compute_loss_with_BCE(self, outputs, masks, labels):
        """
        Uses weighted BCE to calculate loss
        """
        labels = torch.autograd.Variable(labels.view(-1))
        masks = torch.autograd.Variable(masks.view(-1))
        outputs = outputs.mul(masks)
        labels = labels.mul(masks)

        w1 = labels.sum()/labels.nelement()
        w0 = 1.0 - w1
        weights = labels.mul(w0.expand(labels.size(0))) + (1-labels).mul(w1.expand(labels.size(0)))

        criterion = torch.nn.BCELoss(weight=weights.data)
        loss = criterion(outputs, labels)
        return loss

    def compute_loss(self, outputs, masks, labels):
        """
        Our implementation of weighted BCE loss.
        """
        labels = labels.view(-1)
        masks = masks.view(-1)

        # Generate the weights
        ones = torch.sum(labels)
        total = labels.nelement()
        weights = torch.FloatTensor(outputs.size()).type_as(outputs.data)
        weights[labels.long() == 1] = 1.0-ones/total
        weights[labels.long() == 0] = ones/total
        weights = weights.view(weights.size(0), 1).expand(weights.size(0), 2)

        # Generate the log outputs
        outputs = outputs.clamp(min=1e-8)
        log_outputs = torch.log(outputs)
        neg_outputs = 1.0-outputs
        neg_outputs = neg_outputs.clamp(min=1e-8)
        neg_log_outputs = torch.log(neg_outputs)
        all_outputs = torch.cat((log_outputs.view(-1, 1), neg_log_outputs.view(-1, 1)), 1)

        all_values = all_outputs.mul(torch.autograd.Variable(weights))
        all_labels = torch.autograd.Variable(torch.cat((labels, 1.0-labels), 1))
        all_masks = torch.autograd.Variable(masks.view(-1, 1).expand(masks.size(0), 2))
        loss = -torch.sum(all_values.mul(all_labels).mul(all_masks))/outputs.size(0)
        return loss