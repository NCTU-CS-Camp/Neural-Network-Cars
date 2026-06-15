import random


def mutateOneWeightGene(parent1, child1):
    sizenn = len(child1.sizes)

    for i in range(sizenn - 1):
        for j in range(child1.sizes[i + 1]):
            for k in range(child1.sizes[i]):
                child1.weights[i][j][k] = parent1.weights[i][j][k]

    for i in range(sizenn - 1):
        for j in range(child1.sizes[i + 1]):
            child1.biases[i][j] = parent1.biases[i][j]

    genomeWeights = []

    for i in range(sizenn - 1):
        for j in range(child1.sizes[i] * child1.sizes[i + 1]):
            genomeWeights.append(child1.weights[i].item(j))

    r1 = random.randint(0, len(genomeWeights) - 1)
    genomeWeights[r1] = genomeWeights[r1] * random.uniform(0.8, 1.2)

    count = 0
    for i in range(sizenn - 1):
        for j in range(child1.sizes[i + 1]):
            for k in range(child1.sizes[i]):
                child1.weights[i][j][k] = genomeWeights[count]
                count += 1


def mutateOneBiasesGene(parent1, child1):
    sizenn = len(child1.sizes)

    for i in range(sizenn - 1):
        for j in range(child1.sizes[i + 1]):
            for k in range(child1.sizes[i]):
                child1.weights[i][j][k] = parent1.weights[i][j][k]

    for i in range(sizenn - 1):
        for j in range(child1.sizes[i + 1]):
            child1.biases[i][j] = parent1.biases[i][j]

    genomeBiases = []

    for i in range(sizenn - 1):
        for j in range(child1.sizes[i + 1]):
            genomeBiases.append(child1.biases[i].item(j))

    r1 = random.randint(0, len(genomeBiases) - 1)
    genomeBiases[r1] = genomeBiases[r1] * random.uniform(0.8, 1.2)

    count = 0
    for i in range(sizenn - 1):
        for j in range(child1.sizes[i + 1]):
            child1.biases[i][j] = genomeBiases[count]
            count += 1


def uniformCrossOverWeights(parent1, parent2, child1, child2):
    sizenn = len(child1.sizes)

    for i in range(sizenn - 1):
        for j in range(child1.sizes[i + 1]):
            for k in range(child1.sizes[i]):
                child1.weights[i][j][k] = parent1.weights[i][j][k]

    for i in range(sizenn - 1):
        for j in range(child1.sizes[i + 1]):
            for k in range(child1.sizes[i]):
                child2.weights[i][j][k] = parent2.weights[i][j][k]

    for i in range(sizenn - 1):
        for j in range(child2.sizes[i + 1]):
            child1.biases[i][j] = parent1.biases[i][j]

    for i in range(sizenn - 1):
        for j in range(child2.sizes[i + 1]):
            child2.biases[i][j] = parent2.biases[i][j]

    genome1 = []
    genome2 = []

    for i in range(sizenn - 1):
        for j in range(child1.sizes[i] * child1.sizes[i + 1]):
            genome1.append(child1.weights[i].item(j))

    for i in range(sizenn - 1):
        for j in range(child2.sizes[i] * child2.sizes[i + 1]):
            genome2.append(child2.weights[i].item(j))

    alter = True
    for i in range(len(genome1)):
        if alter:
            aux = genome1[i]
            genome1[i] = genome2[i]
            genome2[i] = aux
            alter = False
        else:
            alter = True

    count = 0
    for i in range(sizenn - 1):
        for j in range(child1.sizes[i + 1]):
            for k in range(child1.sizes[i]):
                child1.weights[i][j][k] = genome1[count]
                count += 1

    count = 0
    for i in range(sizenn - 1):
        for j in range(child2.sizes[i + 1]):
            for k in range(child2.sizes[i]):
                child2.weights[i][j][k] = genome2[count]
                count += 1


def uniformCrossOverBiases(parent1, parent2, child1, child2):
    sizenn = len(parent1.sizes)

    for i in range(sizenn - 1):
        for j in range(child1.sizes[i + 1]):
            for k in range(child1.sizes[i]):
                child1.weights[i][j][k] = parent1.weights[i][j][k]

    for i in range(sizenn - 1):
        for j in range(child1.sizes[i + 1]):
            for k in range(child1.sizes[i]):
                child2.weights[i][j][k] = parent2.weights[i][j][k]

    for i in range(sizenn - 1):
        for j in range(child2.sizes[i + 1]):
            child1.biases[i][j] = parent1.biases[i][j]

    for i in range(sizenn - 1):
        for j in range(child2.sizes[i + 1]):
            child2.biases[i][j] = parent2.biases[i][j]

    genome1 = []
    genome2 = []

    for i in range(sizenn - 1):
        for j in range(child1.sizes[i + 1]):
            genome1.append(child1.biases[i].item(j))

    for i in range(sizenn - 1):
        for j in range(child2.sizes[i + 1]):
            genome2.append(child2.biases[i].item(j))

    alter = True
    for i in range(len(genome1)):
        if alter:
            aux = genome1[i]
            genome1[i] = genome2[i]
            genome2[i] = aux
            alter = False
        else:
            alter = True

    count = 0
    for i in range(sizenn - 1):
        for j in range(child1.sizes[i + 1]):
            child1.biases[i][j] = genome1[count]
            count += 1

    count = 0
    for i in range(sizenn - 1):
        for j in range(child2.sizes[i + 1]):
            child2.biases[i][j] = genome2[count]
            count += 1
